"""WT-19 reproducible violence measurement harness (S-02 scoped).

Runs model/window/ensemble measurements and dumps JSON artifacts for the
EXP-19xx cards. Measurement runs require the campaign RESOURCE-LOCK protocol.

Usage (from repo root, venv python):
  python backend/tests/wt19_sweep_harness.py identity  --weights backend/best_model.pt
  python backend/tests/wt19_sweep_harness.py throughput --weights backend/best_model.pt --device cuda
  python backend/tests/wt19_sweep_harness.py sweep     --weights backend/best_model.pt --device cuda
  python backend/tests/wt19_sweep_harness.py scores    --weights backend/best_model.pt --device cuda \
      --videos demo_assets/videos --out scores.json
  python backend/tests/wt19_sweep_harness.py compare baseline_scores.json branch_scores.json

`scores` records per-window score sequences with the fields WT-20 requested
(raw margin + smoothed + ensemble + identity fields); `compare` diffs two runs
(score parity before/after). No accuracy/FP claims: demo AVIs are unlabeled
(source mode `file-media`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def _load_inference(backend_path: Path | None):
    backend = (backend_path or (ROOT / "backend")).resolve()
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    import inference  # noqa: E402
    return inference


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _code_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "unknown"


def _percentiles(samples_ms: list[float]) -> dict:
    ordered = sorted(samples_ms)
    def pct(p):
        if not ordered:
            return None
        idx = min(len(ordered) - 1, max(0, int(round(p / 100 * (len(ordered) - 1)))))
        return ordered[idx]
    return {
        "n": len(ordered),
        "p05_ms": pct(5),
        "median_ms": pct(50),
        "p95_ms": pct(95),
        "mean_ms": statistics.fmean(ordered) if ordered else None,
        "min_ms": ordered[0] if ordered else None,
        "max_ms": ordered[-1] if ordered else None,
    }


def _sync(device):
    import torch
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def _build_model(inference, arch: str, weights: Path, device):
    import torch
    if arch == "slowfast":
        ckpt = torch.load(str(weights), map_location="cpu", weights_only=True)
        state = inference.ViolenceInferencePipeline._extract_state_dict(ckpt)
        model = inference.ViolenceDetector(num_classes=2)
        model.load_state_dict(state)
    elif arch == "r2plus1d":
        # No trained R(2+1)D checkpoint exists in the repo (verified 2026-09-29);
        # random-init model measures architecture throughput ONLY.
        model = inference.X3DViolenceModel(num_classes=2)
    else:
        raise ValueError(arch)
    model = model.to(device).eval()
    return model


class InfeasibleWindow(RuntimeError):
    """Raised when an architecture cannot accept a window length.

    Measured case: the shipped pytorchvideo slowfast_r50 slow pathway requires
    T_slow = window/4 >= 8 (final avg_pool3d kernel 8), so window <= 16 cannot
    run on that backbone at all.
    """


def _forward(inference, model, arch: str, window_frames, device):
    import torch
    try:
        if arch == "slowfast":
            fast_cpu = inference.preprocess_slowfast_window(window_frames)
            fast = fast_cpu.to(device)
            slow = fast[:, ::4, :, :, :]
            with torch.inference_mode():
                return model(slow, fast)
        inputs = inference.preprocess_window(window_frames).to(device)
        with torch.inference_mode():
            return model(inputs)
    except RuntimeError as exc:
        message = str(exc)
        if ("smaller than kernel size" in message or "avg_pool3d" in message
                or "Sizes of tensors must match" in message):
            raise InfeasibleWindow(message.splitlines()[-1]) from exc
        raise


def _random_window(inference, window_size: int):
    size = inference.SLOWFAST_FRAME_SIZE
    rng = np.random.default_rng(1234)
    return [rng.integers(0, 255, (size, size, 3), dtype=np.uint8) for _ in range(window_size)]


def cmd_identity(args) -> dict:
    inference = _load_inference(args.backend_path)
    import torch
    weights = Path(args.weights)
    ckpt = torch.load(str(weights), map_location="cpu", weights_only=True)
    state = inference.ViolenceInferencePipeline._extract_state_dict(ckpt)
    identity = inference.identify_checkpoint(state)
    slowfast_params = sum(p.numel() for p in inference.ViolenceDetector(num_classes=2).parameters())
    r2p1_params = sum(p.numel() for p in inference.X3DViolenceModel(num_classes=2).parameters())
    return {
        "mode": "identity",
        "code_sha": _code_sha(),
        "weights": str(weights),
        "weights_sha256": _sha256(weights),
        "weights_bytes": weights.stat().st_size,
        "checkpoint_identity": identity,
        "checkpoint_meta": {
            key: ckpt.get(key) for key in
            ("epoch", "git_commit", "best_f1", "best_balanced_accuracy", "best_loss")
            if isinstance(ckpt, dict)
        },
        "slowfast_params": slowfast_params,
        "r2plus1d_params": r2p1_params,
        "removed_dead_stn_params": 512000 * 32 + 32 + 32 * 6 + 6,
        "source_mode": "checkpoint-file",
    }


def cmd_throughput(args) -> dict:
    inference = _load_inference(args.backend_path)
    import torch
    device = torch.device(args.device)
    results = {"mode": "throughput", "code_sha": _code_sha(),
               "weights": args.weights, "weights_sha256": _sha256(Path(args.weights)),
               "device": args.device, "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else None,
               "source_mode": "synthetic-random-windows", "arch": {}, "preprocess": {}}
    for arch in ("slowfast", "r2plus1d"):
        model = _build_model(inference, arch, Path(args.weights), device)
        for window_size in args.windows:
            key = f"{arch}_window{window_size}"
            weights_note = ("shipped-checkpoint" if arch == "slowfast"
                            else "RANDOM-INIT (no trained R(2+1)D weights exist)")
            frames = _random_window(inference, window_size)
            try:
                _forward(inference, model, arch, frames, device)  # cold (also feasibility probe)
            except InfeasibleWindow as exc:
                results["arch"][key] = {"feasible": False, "error": str(exc)[:200],
                                        "weights_note": weights_note}
                continue
            _sync(device)
            t0 = time.perf_counter()
            _forward(inference, model, arch, frames, device)
            _sync(device)
            cold_ms = (time.perf_counter() - t0) * 1000
            pre = []
            for _ in range(5):
                t0 = time.perf_counter()
                if arch == "slowfast":
                    inference.preprocess_slowfast_window(frames)
                else:
                    inference.preprocess_window(frames)
                pre.append((time.perf_counter() - t0) * 1000)
            warm = []
            for _ in range(args.iters):
                t0 = time.perf_counter()
                _forward(inference, model, arch, frames, device)
                _sync(device)
                warm.append((time.perf_counter() - t0) * 1000)
            results["arch"][key] = {
                "feasible": True,
                "cold_ms": cold_ms,
                "warm": _percentiles(warm),
                "preprocess_ms": _percentiles(pre),
                "completed_inferences_per_s": 1000 / statistics.median(warm),
                "weights_note": weights_note,
            }
        del model
        if device.type == "cuda":
            torch.cuda.empty_cache()
    return results


SWEEP_GRID = [(16, 4), (16, 8), (16, 16), (32, 4), (32, 8), (32, 16), (64, 16), (64, 32)]
OVERLAP_VARIANT = {"name": "overlap50", "window": 32, "stride": 16,
                   "ensemble_k": 2, "ensemble_agg": "max",
                   "note": "50% overlap via 2 half-stride-offset ensemble members"}


def cmd_sweep(args) -> dict:
    inference = _load_inference(args.backend_path)
    import torch
    device = torch.device(args.device)
    results = {"mode": "sweep", "code_sha": _code_sha(),
               "weights": args.weights, "weights_sha256": _sha256(Path(args.weights)),
               "device": args.device, "source_mode": "synthetic-30fps-stream + random windows",
               "g04_budget_ms": {"p50": 1200, "p95": 2000}, "cells": []}
    model = _build_model(inference, "slowfast", Path(args.weights), device)
    fps = float(args.fps)
    for window_size, stride in SWEEP_GRID:
        # Window validity rate on a clean 30 fps synthetic stream and on a
        # stream with 5% duplicate-stamp drops (clock disorder).
        stamps_clean = [i / fps for i in range(600)]
        stamps_dirty = [t + (0.002 if (i % 20 == 0) else 0.0) for i, t in enumerate(stamps_clean)]
        stamps_dirty = [t if (i % 23) else t - 0.5 for i, t in enumerate(stamps_dirty)]

        def valid_rate(stamps):
            window_stamps = inference.deque(maxlen=window_size)
            valid = 0
            total = 0
            for t in stamps:
                window_stamps.append(t)
                if len(window_stamps) == window_size:
                    total += 1
                    if inference.assess_window_integrity(list(window_stamps), window_size, fps)["valid"]:
                        valid += 1
            return {"valid": valid, "total": total,
                    "rate": valid / total if total else None}

        frames = _random_window(inference, window_size)
        inference_ms = None
        p95_ms = None
        infeasible = None
        try:
            _forward(inference, model, "slowfast", frames, device)
            _sync(device)
            warm = []
            for _ in range(args.iters):
                t0 = time.perf_counter()
                _forward(inference, model, "slowfast", frames, device)
                _sync(device)
                warm.append((time.perf_counter() - t0) * 1000)
            inference_ms = statistics.median(warm)
            p95_ms = _percentiles(warm)["p95_ms"]
        except InfeasibleWindow as exc:
            infeasible = str(exc)[:200]
        window_span_s = (window_size - 1) / fps
        quant_s = stride / fps
        ema_ramp_s = quant_s  # one extra stride at alpha 0.45 (starts only after frame N)
        n_of_m_s = 2 * quant_s  # confirm_n=2 of confirm_m=3 (decision layer, WT-20)
        floor_s = window_span_s + quant_s + ema_ramp_s + n_of_m_s
        cell = {
            "window": window_size, "stride": stride,
            "feasible_on_shipped_slowfast": infeasible is None,
            "infeasibility_reason": infeasible,
            "window_span_s": window_span_s,
            "window_span_pct_of_g04_p50": 100 * window_span_s * 1000 / 1200,
            "scoring_period_s": quant_s,
            "ema_ramp_s": ema_ramp_s,
            "n_of_m_confirmation_s": n_of_m_s,
            "implied_glass_to_alert_floor_s_before_inference": floor_s,
            "model_inference_ms_median": inference_ms,
            "model_inference_ms_p95": p95_ms,
            "implied_floor_plus_inference_s": (floor_s + inference_ms / 1000) if inference_ms else None,
            "inferences_per_s": (1000 / inference_ms) if inference_ms else None,
            "window_valid_rate_clean": valid_rate(stamps_clean),
            "window_valid_rate_disordered": valid_rate(stamps_dirty),
            "g04_p50_budget_met_before_fusion": (
                (floor_s + inference_ms / 1000) <= 1.2 if inference_ms else None
            ),
        }
        results["cells"].append(cell)
    results["overlap_variant"] = {
        **OVERLAP_VARIANT,
        "scoring_period_s": OVERLAP_VARIANT["stride"] / fps,
        "extra_model_forwards_per_completion": 0,
        "note_extra": "ensemble aggregates completed window scores; no extra forward (R4 design)",
    }
    return results


def _supports_kwargs(inference, *names) -> bool:
    """True iff the imported revision's `_infer_window_async` accepts these params."""
    import inspect
    params = inspect.signature(
        inference.ViolenceInferencePipeline._infer_window_async).parameters
    return all(name in params for name in names)


def _make_pipeline(inference, weights, device, **requested):
    """Construct the pipeline passing only kwargs the revision supports.

    Baseline revisions predate window_size/ensemble_*; parity runs must still
    construct on both revisions.
    """
    import inspect
    params = inspect.signature(inference.ViolenceInferencePipeline.__init__).parameters
    supported = {k: v for k, v in requested.items() if k in params and k != "self"}
    dropped = sorted(set(requested) - set(supported))
    if dropped:
        print(f"[harness] revision does not support kwargs {dropped}; using defaults", file=sys.stderr)
    return inference.ViolenceInferencePipeline(weights, device, **supported)


def cmd_scores(args) -> dict:
    """Stream demo AVI frames through the pipeline (real ingress path).

    Records per-clip probes (`_last_conf` / raw / calibrated / window_status)
    that exist on BOTH baseline and branch revisions, plus the branch-side
    per-window score history when present. Unlabelled file-media: no accuracy
    or FP claims are derivable from this mode.
    """
    inference = _load_inference(args.backend_path)
    import cv2
    import torch
    device = torch.device(args.device)
    pipeline = _make_pipeline(
        inference, args.weights, device, threshold=args.threshold,
        stride=args.stride, window_size=args.window,
        ensemble_k=args.ensemble_k, ensemble_agg=args.ensemble_agg,
    )
    pipeline._motion_gate_mode = args.motion_gate
    pipeline._motion_gate_floor = args.motion_floor
    records = []
    probes = []
    history_seen = 0
    videos = sorted(Path(args.videos).glob("*.avi"))
    t0_all = time.perf_counter()
    for video in videos:
        cap = cv2.VideoCapture(str(video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        fed = 0
        t0 = time.perf_counter()
        while fed < args.max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            pipeline.process_frame(frame, captured_at=fed / fps, nominal_fps=fps)
            fed += 1
        cap.release()
        deadline = time.time() + 120
        while getattr(pipeline, "_inference_running", False) and time.time() < deadline:
            time.sleep(0.005)
        feed_ms = (time.perf_counter() - t0) * 1000
        status = dict(getattr(pipeline, "window_status", {}) or {})
        probes.append({
            "clip_id": video.name,
            "frames_fed": fed,
            "fps": fps,
            "feed_wall_ms": feed_ms,
            "observation_id": getattr(pipeline, "_observation_id", None),
            "last_conf": getattr(pipeline, "_last_conf", None),
            "raw_conf": getattr(pipeline, "_last_raw_conf", None),
            "calibrated_conf": getattr(pipeline, "_last_calibrated_conf", None),
            "is_violent": getattr(pipeline, "_is_violent", None),
            "window_id": status.get("window_id"),
            "window_valid": status.get("valid"),
            "span_seconds": status.get("span_seconds"),
            "frames_required": status.get("frames_required"),
            "onset_candidate_timestamp": status.get("onset_candidate_timestamp"),
            "onset_candidate_window_id": status.get("onset_candidate_window_id"),
            "motion_energy": status.get("motion_energy"),
            "motion_gated": status.get("motion_gated"),
            "ensemble_score": status.get("ensemble_score"),
            "ensemble_spread": status.get("ensemble_spread"),
        })
        history = list(getattr(pipeline, "_window_score_history", []) or [])
        for row in history[history_seen:]:
            tagged = dict(row)
            tagged["clip_id"] = video.name
            records.append(tagged)
        history_seen = len(history)
    pipeline._inference_executor.shutdown(wait=True)
    return {
        "mode": "scores",
        "code_sha": _code_sha(),
        "weights_sha256": _sha256(Path(args.weights)),
        "source_mode": "file-media (demo AVIs, UNLABELLED — no accuracy/FP claims)",
        "label_source": "none",
        "window": args.window, "stride": args.stride,
        "ensemble_k": args.ensemble_k, "ensemble_agg": args.ensemble_agg,
        "motion_gate": args.motion_gate, "motion_floor": args.motion_floor,
        "threshold": args.threshold,
        "max_frames_per_clip": args.max_frames,
        "n_windows": len(records), "n_clips": len(videos),
        "n_probes": len(probes),
        "wall_clock_s": time.perf_counter() - t0_all,
        "probes": probes,
        "window_scores": records,
    }


def cmd_window_scores(args) -> dict:
    """Deterministic score parity: score FIXED windows synchronously.

    Bypasses the async ingress (whose completion count depends on feed vs
    inference pacing) and calls `_infer_window_async` directly on identical
    frame windows, so baseline/branch score comparison is exact. Works on both
    revisions: baseline's signature is (window_frames, observed_at, generation,
    source_captured_at).
    """
    inference = _load_inference(args.backend_path)
    import cv2
    import torch
    device = torch.device(args.device)
    pipeline = _make_pipeline(
        inference, args.weights, device, threshold=args.threshold,
        stride=args.stride, window_size=args.window,
        ensemble_k=args.ensemble_k, ensemble_agg=args.ensemble_agg,
    )
    pipeline._motion_gate_mode = args.motion_gate
    pipeline._motion_gate_floor = args.motion_floor
    records = []
    videos = sorted(Path(args.videos).glob("*.avi"))
    for video in videos:
        cap = cv2.VideoCapture(str(video))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = []
        while len(frames) < args.max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(frame)
        cap.release()
        index = 0
        supports_integrity = _supports_kwargs(
            inference, "window_id", "window_start_timestamp", "window_end_timestamp", "window_integrity")
        for start in range(0, max(0, len(frames) - args.window + 1), args.window):
            window = frames[start:start + args.window]
            index += 1
            if supports_integrity:
                stamps = [(start + i) / fps for i in range(len(window))]
                integrity = inference.assess_window_integrity(stamps, len(window), fps)
                pipeline._infer_window_async(
                    window,
                    start / fps,
                    None,
                    start / fps,
                    index,
                    stamps[0],
                    stamps[-1],
                    {
                        "valid": integrity["valid"],
                        "frames_collected": len(window),
                        "frames_required": args.window,
                        "span_seconds": integrity["span_seconds"],
                    },
                )
            else:
                # Baseline revisions accept only the original four arguments.
                pipeline._infer_window_async(window, start / fps, None, start / fps)
            completed = dict(getattr(pipeline, "_completed_window_fields", {}) or {})
            records.append({
                "clip_id": video.name,
                "window_index": index,
                "observation_id": getattr(pipeline, "_observation_id", None),
                "window_start_timestamp": start / fps,
                "window_end_timestamp": (start + args.window - 1) / fps,
                "raw_conf": getattr(pipeline, "_last_raw_conf", None),
                "calibrated_conf": getattr(pipeline, "_last_calibrated_conf", None),
                "smoothed_conf": getattr(pipeline, "_last_conf", None),
                "label": getattr(pipeline, "_last_label", None),
                "is_violent": getattr(pipeline, "_is_violent", None),
                "ensemble_score": completed.get("ensemble_score"),
                "ensemble_spread": completed.get("ensemble_spread"),
                "motion_energy": completed.get("motion_energy"),
                "motion_gated": completed.get("motion_gated"),
                "logit_margin": completed.get("logit_margin"),
                "window_valid": completed.get("window_valid"),
                "window_frames_collected": completed.get("window_frames_collected"),
                "window_frames_required": completed.get("window_frames_required"),
                "window_span_seconds": completed.get("window_span_seconds"),
                "onset_candidate_timestamp": getattr(pipeline, "_onset_candidate_timestamp", None),
                "onset_candidate_window_id": getattr(pipeline, "_onset_candidate_window_id", None),
            })
    pipeline._inference_executor.shutdown(wait=True)
    return {
        "mode": "window-scores",
        "code_sha": _code_sha(),
        "weights_sha256": _sha256(Path(args.weights)),
        "source_mode": "file-media deterministic fixed windows (demo AVIs, UNLABELLED)",
        "label_source": "none",
        "window": args.window, "stride": args.stride,
        "ensemble_k": args.ensemble_k, "ensemble_agg": args.ensemble_agg,
        "motion_gate": args.motion_gate, "motion_floor": args.motion_floor,
        "threshold": args.threshold,
        "n_windows": len(records),
        "n_clips": len(videos),
        "window_scores": records,
    }


def build_fixture_outputs(manifest: dict, scores: dict, run_id: str) -> tuple[list[dict], list[str]]:
    """Map WT-19 window-score records onto WT-12's recorded-outputs contract.

    Contract source: wt-12 `bench/eval/contracts.py` (`load_outputs`). Required
    per record: `fixture_id` (must exist in the manifest), `source_sha256` equal
    to the manifest's `media.sha256`, `source_mode` != "live", and `windows[]`
    items with `start_s >= 0`, `end_s > start_s`, `violence_conf` in [0, 1].
    Extra keys are permitted and are carried additively (WT-12 runtime_contract
    names `valid`, `frames_collected`, `frames_required`, `span_s`).

    Returns (payloads, unmatched_clip_ids). Pure: no file I/O.
    """
    by_clip: dict[str, dict] = {}
    for fixture in manifest.get("fixtures", []):
        media = fixture.get("media") or {}
        raw_path = str(media.get("path") or "")
        for key in {raw_path, Path(raw_path).name}:
            if key:
                by_clip.setdefault(key, fixture)
    grouped: dict[str, tuple[dict, list[dict]]] = {}
    unmatched: list[str] = []
    for row in scores.get("window_scores", []):
        clip = row.get("clip_id")
        fixture = by_clip.get(clip)
        if fixture is None:
            unmatched.append(str(clip))
            continue
        grouped.setdefault(fixture["fixture_id"], (fixture, []))[1].append(row)

    payloads = []
    for fixture_id, (fixture, rows) in sorted(grouped.items()):
        windows = []
        for row in rows:
            start = row.get("window_start_timestamp")
            end = row.get("window_end_timestamp")
            if start is None or end is None or float(end) <= float(start):
                continue
            conf = row.get("smoothed_conf")
            if conf is None:
                conf = row.get("ensemble_score")
            if conf is None:
                conf = row.get("calibrated_conf")
            if conf is None:
                continue
            windows.append({
                "start_s": float(start),
                "end_s": float(end),
                "violence_conf": float(max(0.0, min(1.0, float(conf)))),
                # WT-12 runtime_contract window_integrity_fields
                "valid": row.get("window_valid"),
                "frames_collected": row.get("window_frames_collected"),
                "frames_required": row.get("window_frames_required"),
                "span_s": row.get("window_span_seconds"),
                # additive WT-19 fields (permitted extras; score semantics explicit)
                "raw_conf": row.get("raw_conf"),
                "calibrated_conf": row.get("calibrated_conf"),
                "smoothed_conf": row.get("smoothed_conf"),
                "logit_margin": row.get("logit_margin"),
                "ensemble_k": row.get("ensemble_k"),
                "ensemble_score": row.get("ensemble_score"),
                "ensemble_spread": row.get("ensemble_spread"),
                "motion_energy": row.get("motion_energy"),
                "motion_gated": row.get("motion_gated"),
                "window_id": row.get("window_id"),
            })
        payloads.append({
            "fixture_id": fixture_id,
            "source_sha256": (fixture.get("media") or {}).get("sha256"),
            "run_id": run_id,
            "source_mode": "file-media",
            "windows": sorted(windows, key=lambda w: w["start_s"]),
            "detections": [],
            "alerts": [],
            "tracks": [],
            "producer": {
                "harness": "backend/tests/wt19_sweep_harness.py",
                "code_sha": scores.get("code_sha"),
                "weights_sha256": scores.get("weights_sha256"),
                "window": scores.get("window"), "stride": scores.get("stride"),
                "ensemble_k": scores.get("ensemble_k"), "ensemble_agg": scores.get("ensemble_agg"),
                "motion_gate": scores.get("motion_gate"), "motion_floor": scores.get("motion_floor"),
                "threshold": scores.get("threshold"),
                "producer_source_mode": scores.get("source_mode"),
                "score_semantics": ("violence_conf = EMA-smoothed ensemble output (the decision-relevant score); "
                                    "raw_conf/calibrated_conf are pre-EMA, logit_margin is the raw pre-temperature "
                                    "margin; no calibration artifact was active unless stated in the run config."),
            },
        })
    return payloads, unmatched


def cmd_fixture_outputs(args) -> dict:
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    payloads, unmatched = build_fixture_outputs(manifest, scores, args.run_id)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for payload in payloads:
        path = out_dir / f"{payload['fixture_id']}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written.append({"fixture_id": payload["fixture_id"], "path": str(path),
                        "n_windows": len(payload["windows"])})
    result = {
        "mode": "fixture-outputs",
        "manifest": args.manifest,
        "scores": args.scores,
        "run_id": args.run_id,
        "n_manifest_fixtures": len(manifest.get("fixtures", [])),
        "n_fixtures_written": len(written),
        "written": written,
        "unmatched_clips": sorted(set(unmatched)),
        "strict_enforced": bool(args.strict),
        "strict_ok": not unmatched,
    }
    if args.strict and unmatched:
        raise SystemExit(f"[harness] {len(set(unmatched))} score clip(s) matched no manifest fixture: "
                         f"{sorted(set(unmatched))}")
    return result


def cmd_compare(args) -> dict:
    a = json.loads(Path(args.a).read_text(encoding="utf-8"))
    b = json.loads(Path(args.b).read_text(encoding="utf-8"))
    probe_diff = {}
    for ra, rb in zip(a.get("probes", []), b.get("probes", [])):
        for key in ("last_conf", "raw_conf", "calibrated_conf", "span_seconds", "window_valid", "is_violent"):
            va, vb = ra.get(key), rb.get(key)
            if va is None or vb is None:
                continue
            if isinstance(va, bool) or isinstance(vb, bool):
                probe_diff.setdefault(key, []).append(0.0 if va == vb else 1.0)
            elif isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                probe_diff.setdefault(key, []).append(abs(float(va) - float(vb)))
    window_diff = {}
    for ra, rb in zip(a.get("window_scores", []), b.get("window_scores", [])):
        for key in ("raw_conf", "calibrated_conf", "smoothed_conf", "ensemble_score",
                    "motion_energy", "logit_margin"):
            if ra.get(key) is None or rb.get(key) is None:
                continue
            window_diff.setdefault(key, []).append(abs(float(ra[key]) - float(rb[key])))
    ids_a = [p.get("observation_id") for p in a.get("probes", [])]
    ids_b = [p.get("observation_id") for p in b.get("probes", [])]
    def summarise(diff):
        return {key: {"max_abs_delta": max(vals), "n": len(vals)} for key, vals in diff.items()}
    probe_summary, window_summary = summarise(probe_diff), summarise(window_diff)
    max_delta = max([v["max_abs_delta"] for v in list(probe_summary.values()) + list(window_summary.values())] or [0.0])
    return {
        "mode": "compare",
        "a": args.a, "b": args.b,
        "a_code_sha": a.get("code_sha"), "b_code_sha": b.get("code_sha"),
        "n_probes_a": a.get("n_probes"), "n_probes_b": b.get("n_probes"),
        "observation_ids_a": ids_a, "observation_ids_b": ids_b,
        "observation_ids_match": ids_a == ids_b,
        "n_windows_a": a.get("n_windows"), "n_windows_b": b.get("n_windows"),
        "probe_summary": probe_summary,
        "window_summary": window_summary,
        "max_abs_delta": max_delta,
        "parity_at_1e-4": max_delta <= 1e-4,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-path", type=Path, default=None,
                        help="backend dir whose inference.py to import (default: this repo)")
    parser.add_argument("--out", default=None,
                        help="write pure JSON here (stdout may carry [AI] log lines)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--weights", default=str(ROOT / "backend" / "best_model.pt"))

    p = sub.add_parser("identity", parents=[common])
    p = sub.add_parser("throughput", parents=[common])
    p.add_argument("--device", default="cuda")
    p.add_argument("--iters", type=int, default=30)
    p.add_argument("--windows", type=int, nargs="+", default=[16, 32])

    p = sub.add_parser("sweep", parents=[common])
    p.add_argument("--device", default="cuda")
    p.add_argument("--iters", type=int, default=15)
    p.add_argument("--fps", type=float, default=30.0)

    p = sub.add_parser("scores", parents=[common])
    p.add_argument("--device", default="cuda")
    p.add_argument("--videos", default=str(ROOT / "demo_assets" / "videos"))
    p.add_argument("--window", type=int, default=32)
    p.add_argument("--stride", type=int, default=16)
    p.add_argument("--ensemble-k", type=int, default=1)
    p.add_argument("--ensemble-agg", default="max")
    p.add_argument("--motion-gate", default="off")
    p.add_argument("--motion-floor", type=float, default=1.0)
    p.add_argument("--threshold", type=float, default=0.45)
    p.add_argument("--max-frames", type=int, default=200)

    p = sub.add_parser("window-scores", parents=[common])
    p.add_argument("--device", default="cuda")
    p.add_argument("--videos", default=str(ROOT / "demo_assets" / "videos"))
    p.add_argument("--window", type=int, default=32)
    p.add_argument("--stride", type=int, default=16)
    p.add_argument("--ensemble-k", type=int, default=1)
    p.add_argument("--ensemble-agg", default="max")
    p.add_argument("--motion-gate", default="off")
    p.add_argument("--motion-floor", type=float, default=1.0)
    p.add_argument("--threshold", type=float, default=0.45)
    p.add_argument("--max-frames", type=int, default=256)

    p = sub.add_parser("to-fixture-outputs")
    p.add_argument("--manifest", required=True, help="WT-12 docs/campaign/eval/12-fixture-manifest.json")
    p.add_argument("--scores", required=True, help="window-scores JSON produced by this harness")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--no-strict", dest="strict", action="store_false",
                   help="do not fail when a scored clip matches no manifest fixture")
    p.set_defaults(strict=True)

    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")

    args = parser.parse_args()
    handlers = {"identity": cmd_identity, "throughput": cmd_throughput,
                "sweep": cmd_sweep, "scores": cmd_scores,
                "window-scores": cmd_window_scores,
                "to-fixture-outputs": cmd_fixture_outputs, "compare": cmd_compare}
    result = handlers[args.cmd](args)
    payload = json.dumps(result, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
