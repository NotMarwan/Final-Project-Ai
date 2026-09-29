"""Offline scoring of fixture media with the CURRENT models -> recorded outputs.

Produces one `outputs/<fixture_id>.json` per fixture in the WT-12 recorded-output
schema (windows from the violence model, detections from the weapon model,
tracks from the person model, alerts from a replay of the runtime decision
layer), plus clip/window score exports for calibration consumers.

Measurement protocol:
- GPU runs acquire the campaign RESOURCE-LOCK (atomic mkdir + owner.txt) and
  release it in a finally block. `--no-lock` produces UNMEASURED smoke output
  (marked `measured: false` in the report).
- Source mode is always `file-media`; no camera device exists in this
  environment and no output claims live capture.
- Alert `time_s` is the decision-confirm time: the end of the window whose
  observation confirmed the alert (see docs/campaign/eval/12-eval-protocol.md).

Usage (repository root, campaign venv):
    python -m bench.eval.score_fixtures --manifest docs/campaign/eval/12-fixture-manifest.json \
        --output-dir bench/results/campaign-baseline-2026-09-29/outputs
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from bench.common import BACKEND, ROOT, environment, sha256, write_json

PRIMARY = Path("C:/Users/PCD/Downloads/Final Project AI Sentinel")
RESOURCE_LOCK = Path("C:/Users/PCD/Downloads/jobs/sentinel-campaign/RESOURCE-LOCK")


def resolve_model(relative):
    """Prefer the worktree copy; fall back to the primary checkout (read-only)."""
    local = ROOT / relative
    if local.is_file():
        return local, "worktree"
    primary = PRIMARY / relative
    if primary.is_file():
        return primary, "primary-checkout-read-only"
    raise FileNotFoundError(f"Model asset not found in worktree or primary checkout: {relative}")


def acquire_lock(owner):
    try:
        RESOURCE_LOCK.mkdir()
    except FileExistsError as exc:
        raise RuntimeError(
            f"RESOURCE-LOCK held at {RESOURCE_LOCK}; a concurrent measured run would invalidate this one"
        ) from exc
    (RESOURCE_LOCK / "owner.txt").write_text(
        f"{owner}\nstarted_utc={datetime.now(timezone.utc).isoformat(timespec='seconds')}\n",
        encoding="utf-8")


def release_lock():
    for child in RESOURCE_LOCK.iterdir():
        child.unlink()
    RESOURCE_LOCK.rmdir()


class ViolenceScorer:
    """Window scoring identical to bench/profile_violence.py preprocessing."""

    def __init__(self, weights, device, threshold, stride, window_size):
        import torch
        from inference import ViolenceInferencePipeline, preprocess_slowfast_window
        self.torch = torch
        self.preprocess = preprocess_slowfast_window
        self.pipeline = ViolenceInferencePipeline(str(weights), device, threshold=threshold, stride=stride)
        if not self.pipeline.enabled or self.pipeline.model is None:
            raise RuntimeError(f"Violence model unavailable: {self.pipeline.disabled_reason}")
        self.model = self.pipeline.model.eval()
        self.device = device
        self.window_size = window_size
        self.stride = stride
        self.threshold = threshold

    def score(self, frames):
        import torch.nn.functional as F
        from inference import VIOLENCE_CLS
        with self.torch.inference_mode():
            tensor = self.preprocess(frames)
            fast = tensor.to(self.device)
            slow = fast[:, ::4, :, :, :]
            if self.device.type == "cuda":
                self.torch.cuda.synchronize(self.device)
            logits = self.model(slow, fast)
            if self.device.type == "cuda":
                self.torch.cuda.synchronize(self.device)
            probs = F.softmax(logits, dim=-1)[0]
            return float(probs[VIOLENCE_CLS].item())

    def close(self):
        if hasattr(self.pipeline, "_inference_executor"):
            self.pipeline._inference_executor.shutdown(wait=True)


class WeaponScorer:
    """Frame-sampled weapon detections via the backend ONNX decoder."""

    def __init__(self, model_path, min_confidence=0.20):
        import weapon as weapon_module
        self.backend = weapon_module._ONNXBackend(
            str(model_path), min_confidence=min_confidence,
            labels=("pistol", "rifle", "knife"))
        self.min_confidence = min_confidence

    def detect(self, frame):
        return [{"time_s": None, "class": label, "score": round(float(conf), 6),
                 "bbox": [round(float(v), 2) for v in bbox]}
                for conf, label, bbox in self.backend.predict(frame)]


class PersonScorer:
    """Frame-sampled person tracks via the runtime PersonDetector (IoU tracker).

    Loads eagerly and FAILS LOUDLY: the runtime detector silently disables
    itself when its model is missing (observed 2026-09-29: empty tracks on a
    walking-person clip), which must never become a silent zero in an eval run.
    """

    def __init__(self, conf_threshold=0.45):
        from person_detector import PersonDetector
        self.detector = PersonDetector(conf_threshold=conf_threshold, infer_every_n=1,
                                       device="cpu", min_track_frames=1)
        if not self.detector._load_model() or self.detector._load_error:
            raise RuntimeError(
                f"Person model failed to load ({self.detector._load_error}); "
                "refusing to score with a silently disabled person path")
        self.backend = "onnx" if self.detector._use_onnx else "ultralytics-yolo"

    def detect(self, frame, time_s):
        rows = []
        for track in self.detector.detect(frame):
            rows.append({"time_s": round(time_s, 6), "track_id": track.get("track_id"),
                         "bbox": [round(float(v), 2) for v in track.get("bbox", [])],
                         "confidence": round(float(track.get("confidence", 0.0)), 6)})
        return rows


def score_fixture(fixture, media_root, violence, weapon, person, decision_layer_factory,
                  window_size, stride, frame_stride):
    import cv2
    media = fixture["media"]
    path = Path(media_root) / media["path"]
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open fixture media: {path}")
    fps = float(media["fps"])
    frame_index = 0
    rolling = deque(maxlen=window_size)
    windows = []
    detections = []
    tracks = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            time_s = frame_index / fps
            if frame_index % frame_stride == 0:
                for det in weapon.detect(frame):
                    det["time_s"] = round(time_s, 6)
                    detections.append(det)
                tracks.extend(person.detect(frame, time_s))
            rolling.append(frame)
            if len(rolling) == window_size and (frame_index + 1 - window_size) % stride == 0:
                start_s = (frame_index + 1 - window_size) / fps
                end_s = (frame_index + 1) / fps
                score = violence.score(list(rolling))
                windows.append({
                    "window_id": f"w{len(windows):04d}",
                    "start_s": round(start_s, 6), "end_s": round(end_s, 6),
                    "span_s": round(end_s - start_s, 6),
                    "violence_conf": round(score, 6),
                    "weapon_score": round(max((d["score"] for d in detections
                                               if start_s <= d["time_s"] < end_s), default=0.0), 6),
                    "observation_score": round(score, 6),
                    "valid": True, "clock_source": "file-frame-index",
                    "frames_collected": window_size, "frames_required": window_size,
                })
            frame_index += 1
    finally:
        capture.release()
    # Replay the runtime decision layer over the recorded window observations.
    alerts = []
    layer = decision_layer_factory()
    for index, window in enumerate(windows):
        response = layer.update(window["violence_conf"], sample_time=window["end_s"],
                                sample_id=index, current_time=window["end_s"])
        if response.get("confirmed_alert"):
            alerts.append({
                "alert_id": f"{fixture['fixture_id']}-a{len(alerts):03d}",
                "time_s": window["end_s"],
                "score": window["violence_conf"],
                "type": "Violence", "threat_type": "violence",
                "camera_id": fixture["fixture_id"],
                "decision": {"alert_state": response["alert_state"],
                             "confirm_rule": response["confirm_rule"],
                             "base_model_threshold": response["base_model_threshold"]},
            })
    return {"fixture_id": fixture["fixture_id"], "source_sha256": media["sha256"],
            "source_mode": "file-media",
            "windows": windows, "detections": detections,
            "alerts": alerts, "tracks": tracks,
            "media_facts": {"frames_read": frame_index, "fps": fps}}


def main():
    parser = argparse.ArgumentParser(description="Score WT-12 fixtures with the current models")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--splits", default="test,calibration,val,train",
                        help="comma-separated splits to score")
    parser.add_argument("--fixtures", default="",
                        help="comma-separated fixture_id allowlist (smoke runs)")
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--window-size", type=int, default=32)
    parser.add_argument("--frame-stride", type=int, default=5,
                        help="frames between weapon/person samples")
    parser.add_argument("--no-lock", action="store_true",
                        help="UNMEASURED smoke run without RESOURCE-LOCK")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto",
                        help="force cpu for contention-free smoke runs")
    parser.add_argument("--lock-held", action="store_true",
                        help="caller already holds RESOURCE-LOCK (acquired by pure atomic mkdir; "
                             "owner.txt written after acquisition). Scorer skips acquisition/release.")
    args = parser.parse_args()
    from bench.eval.contracts import load_manifest
    manifest = load_manifest(args.manifest)
    splits = {s.strip() for s in args.splits.split(",") if s.strip()}
    fixtures = [f for f in manifest["fixtures"] if f["split"] in splits]
    allowlist = {f.strip() for f in args.fixtures.split(",") if f.strip()}
    if allowlist:
        fixtures = [f for f in fixtures if f["fixture_id"] in allowlist]
    if not fixtures:
        raise SystemExit("No fixtures match the requested splits")

    import torch
    if args.device == "cpu":
        device = torch.device("cpu")
    elif args.device == "cuda":
        device = torch.device("cuda:0")
    else:
        device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    measured = device.type == "cuda" and not args.no_lock
    if device.type == "cuda" and not args.no_lock and not args.lock_held:
        acquire_lock("WT-12 EvalDataMethodology baseline scoring")
    started = time.monotonic()
    try:
        weights, weights_origin = resolve_model("backend/best_model.pt")
        weapon_path, weapon_origin = resolve_model("backend/models/weapon_yolo.onnx")
        person_path, person_origin = resolve_model("backend/models/person_yolo.onnx")
        import person_detector  # noqa: F401  (backend import path setup below)
        violence = ViolenceScorer(weights, device, threshold=0.45, stride=args.stride,
                                  window_size=args.window_size)
        weapon = WeaponScorer(weapon_path)
        person = PersonScorer()
        from live_alert_decision import LiveAlertDecisionLayer
        from decision_config import load_decision_config
        policy = load_decision_config()

        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        records = []
        for fixture in fixtures:
            record = score_fixture(fixture, manifest["media_root"], violence, weapon, person,
                                   lambda: LiveAlertDecisionLayer(config=policy),
                                   args.window_size, args.stride, args.frame_stride)
            record["run_id"] = out_dir.parent.name
            write_json(out_dir / f"{fixture['fixture_id']}.json", record)
            records.append(record)
        violence.close()

        clip_max = [{"clip_id": r["fixture_id"], "source_sha256": r["source_sha256"],
                     "split": manifest["_by_id"][r["fixture_id"]]["split"],
                     "label": 0 if manifest["_by_id"][r["fixture_id"]]["labels"]["class"] == "benign" else 1,
                     "label_source": manifest["_by_id"][r["fixture_id"]]["labels"]["label_source"],
                     "score": max((w["violence_conf"] for w in r["windows"]), default=0.0),
                     "aggregation": "max"} for r in records]
        clip_mean = [dict(row, score=round(
            sum(w["violence_conf"] for w in r["windows"]) / len(r["windows"]), 6) if r["windows"] else 0.0,
            aggregation="mean") for row, r in zip(clip_max, records)]
        write_json(out_dir.parent / "clip_scores_max.json", clip_max)
        write_json(out_dir.parent / "clip_scores_mean.json", clip_mean)
        # WT-20 (DecisionCalibration) sequences schema, field names exact:
        # {model_sha256, sequences:[{clip_id, source_sha256, split, label, label_source,
        #   scores[], valid[], start_s[]}]} - start_s strictly increasing by construction.
        sequences = []
        for r in records:
            fixture = manifest["_by_id"][r["fixture_id"]]
            windows = sorted(r["windows"], key=lambda w: w["start_s"])
            sequences.append({
                "clip_id": r["fixture_id"], "source_sha256": r["source_sha256"],
                "split": {"val": "dev"}.get(fixture["split"], fixture["split"]),
                "label": 0 if fixture["labels"]["class"] == "benign" else 1,
                "label_source": fixture["labels"]["label_source"],
                "run_id": r.get("run_id"), "source_mode": r["source_mode"],
                "scores": [w["violence_conf"] for w in windows],
                "valid": [w["valid"] for w in windows],
                "start_s": [w["start_s"] for w in windows],
            })
        write_json(out_dir.parent / "window_scores.json", {
            "model_sha256": sha256(weights), "aggregation": "per-window sequences",
            "manifest_schema": "wt12-fixture-manifest/1",
            "runtime_contract": manifest.get("runtime_contract"),
            "sequences": sequences})

        model_hashes = {
            "violence": {"path": str(weights), "sha256": sha256(weights), "provenance": weights_origin},
            "weapon": {"path": str(weapon_path), "sha256": sha256(weapon_path), "provenance": weapon_origin},
            "person": {"path": str(person_path), "sha256": sha256(person_path), "provenance": person_origin,
                       "runtime_backend": person.backend},
        }
        report = {
            "run_id": out_dir.parent.name,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "measured": measured,
            "measurement_note": (
                "RESOURCE-LOCK held for the whole run" if measured and not args.lock_held else
                "RESOURCE-LOCK acquired by caller via pure atomic mkdir before this run and released by "
                "the caller afterwards (owner.txt written at acquisition)" if measured else
                "UNMEASURED smoke run (--no-lock or CPU device); never a baseline"),
            "resource_lock": ("acquired-by-caller" if args.lock_held and measured
                              else "acquired-by-scorer" if measured else "not-held(unmeasured)"),
            "code": {"revision": environment()["revision"], "branch": environment()["branch"]},
            "models": model_hashes,
            "preprocessing": {
                "violence": "backend.inference.preprocess_slowfast_window (SlowFast slow=stride-4 subsample)",
                "window_frames": args.window_size, "stride_frames": args.stride,
                "weapon_person_sampling": f"every {args.frame_stride} frames",
                "weapon_person_rows": ("ABSENT by construction (anchor-pass1: sampling cadence exceeds clip "
                                       "length); not zero detections - unmeasured in this pass"
                                       if args.frame_stride >= 1000 else "present at the stated cadence"),
            },
            "decision_config": policy.to_dict(),
            "decision_replay": ("backend.live_alert_decision.LiveAlertDecisionLayer over RAW window "
                                "scores (no EMA smoothing); alert time = confirming window end"),
            "dataset": {"manifest": args.manifest,
                        "manifest_sha256": sha256(args.manifest),
                        "splits": sorted(splits),
                        "fixtures": sorted(r["fixture_id"] for r in records)},
            "environment": environment(),
            "source_mode": "file-media",
            "adapter_state": ("offline scoring: no API harness; go2rtc_bridge/openrouter_reporting "
                              "absent and not loaded (SC-10)"),
            "device": str(device),
            "wall_seconds": round(time.monotonic() - started, 3),
            "outputs_dir": str(out_dir),
        }
        write_json(out_dir.parent / "report.json", report)
        print(json.dumps({"fixtures_scored": len(records), "device": str(device),
                          "measured": measured, "output_dir": str(out_dir)}, indent=2))
        return 0
    finally:
        if device.type == "cuda" and not args.no_lock and not args.lock_held:
            release_lock()


if __name__ == "__main__":
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    raise SystemExit(main())
