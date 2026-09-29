"""Offline FP-logging run over a negatives clip set (WT-07 rec #1, step 1).

Runs the registered weapon path at its real operating point over each clip,
logs EVERY weapon-path detection as a false positive (the source is declared
benign), writes crops + JSONL rows, and summarizes the run with explicit
denominators.

Usage (from the repo root, venv python):
    python backend/tools/weapon_fp_log_run.py \
        --clips <dir-or-file> [<dir-or-file> ...] \
        --out   <log-dir> \
        --source-label kth-aux-negatives \
        --policy-json '{"weapon_min_confidence": 0.20, ...}'   # only while SC-5 keys are pending

`--policy-json` exists only so an auxiliary run can proceed before the SC-5
`config/thresholds.toml` weapon keys land; when omitted the tool uses the
single threshold authority (`load_decision_policy`). Every value actually
used is recorded in each row's `context`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

TOOLS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TOOLS_DIR.parent
for path in (str(BACKEND_DIR), str(TOOLS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402

import weapon  # noqa: E402
from weapon_eval import summarize_negative_run  # noqa: E402
from weapon_fp_log import WeaponFPLogger, validate_fp_record  # noqa: E402

VIDEO_SUFFIXES = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".m4v"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def iter_media(clips: list[Path]) -> list[Path]:
    media: list[Path] = []
    for item in clips:
        if item.is_dir():
            media.extend(sorted(p for p in item.rglob("*")
                                if p.suffix.lower() in VIDEO_SUFFIXES | IMAGE_SUFFIXES))
        elif item.is_file():
            media.append(item)
        else:
            raise SystemExit(f"clip path not found: {item}")
    return media


def select_media(media: list[Path], manifest_index: dict[str, dict],
                 fixture_filter: str | None) -> list[Path]:
    """Restrict the run to manifest fixtures whose id contains `fixture_filter`.

    With a filter set, media that resolve to no manifest fixture are excluded
    (never silently treated as part of a declared suite).
    """
    if not fixture_filter:
        return media
    selected = []
    for path in media:
        identity = manifest_index.get(sha256_file(path), {})
        fixture_id = str(identity.get("fixture_id", ""))
        if fixture_id and fixture_filter in fixture_id:
            selected.append(path)
    return selected


def load_manifest(path: Path | None) -> dict[str, dict]:
    """Optional WT-12 manifest: maps media sha256 -> fixture identity."""
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    index: dict[str, dict] = {}
    for fixture in payload.get("fixtures", []):
        digest = str(fixture.get("media", {}).get("sha256", ""))
        if digest:
            index[digest] = {
                "fixture_id": fixture.get("fixture_id"),
                "split": fixture.get("split", "unregistered"),
            }
    return index


def wt12_output_record(*, fixture_id: str, source_sha256: str, run_id: str,
                       rows: list[dict], alert_threshold: float) -> dict:
    """Run output in the WT-12 `outputs` schema (bench/eval/contracts.load_outputs).

    Only manifest-registered fixtures are emittable: the validator requires
    `fixture_id` to resolve and `source_sha256` to equal the manifest media
    hash, so unregistered auxiliary media must never be presented as a run.
    """
    if fixture_id.startswith("unregistered:"):
        raise SystemExit(
            f"refusing to emit WT-12 outputs for unregistered media ({fixture_id}); "
            "register the fixture in the WT-12 manifest first")
    detections = [{
        "time_s": float(row["time_s"]),
        "class": str(row["class"]),
        "score": float(row["score"]),
        "bbox": [float(value) for value in row["bbox_px"]],
        "canonical_label": row["canonical_label"],
        "group": row["group"],
    } for row in rows]
    alerts = [{
        "alert_id": f"{fixture_id}:{row['log_id']}",
        "time_s": float(row["time_s"]),
        "score": float(row["score"]),
        "class": str(row["class"]),
    } for row in rows if float(row["score"]) >= alert_threshold]
    return {
        "fixture_id": fixture_id,
        "source_sha256": source_sha256,
        "run_id": run_id,
        "source_mode": "file-media",
        "windows": [],
        "detections": detections,
        "alerts": alerts,
        "tracks": [],
        "model_sha256": rows[0].get("context", {}).get("model_sha256") if rows else None,
    }


def policy_from_args(raw: str | None):
    """Explicit operator-supplied knobs (recorded in the log context)."""
    if raw is None:
        return weapon.load_decision_policy(), None
    values = json.loads(raw)
    required = set(weapon._POLICY_FIELDS.values())
    missing = sorted(required - set(values))
    if missing:
        raise SystemExit(f"--policy-json is missing required keys: {missing}")
    if set(values) - required:
        raise SystemExit(f"--policy-json has unknown keys: {sorted(set(values) - required)}")
    return SimpleNamespace(**values), "cli"


def frames_from_clip(path: Path, stride: int):
    if path.suffix.lower() in IMAGE_SUFFIXES:
        image = cv2.imread(str(path))
        if image is None:
            raise SystemExit(f"unreadable image: {path}")
        yield 0, 0.0, image
        return
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise SystemExit(f"unreadable video: {path}")
    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % stride == 0:
                yield index, (index / fps if fps > 0 else 0.0), frame
            index += 1
    finally:
        capture.release()


def run(args) -> dict:
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    policy, policy_source = policy_from_args(args.policy_json)
    manifest_index = load_manifest(Path(args.manifest) if args.manifest else None)
    media = iter_media([Path(item) for item in args.clips])
    media = select_media(media, manifest_index, getattr(args, "fixture_filter", None))
    if not media:
        raise SystemExit("no media found under --clips (after --fixture-filter)")

    run_rows: list[dict] = []
    clip_summaries: list[dict] = []
    for path in media:
        digest = sha256_file(path)
        identity = manifest_index.get(digest, {})
        config = weapon.WeaponConfig.from_settings(
            {}, {},
            policy=policy,
        ) if not args.min_confidence_override else weapon.WeaponConfig.from_settings(
            {}, {"WEAPON_MIN_CONFIDENCE": str(args.min_confidence_override)}, policy=policy)
        engine = weapon.WeaponSignalEngine(config, device=torch.device(args.device))
        first = next(frames_from_clip(path, max(1, args.stride)), None)
        if first is None:
            continue
        _, _, sample = first
        height, width = sample.shape[:2]
        logger = WeaponFPLogger(
            root=out_root,
            clip_id=f"{path.stem}",
            source=args.source_label or str(path),
            source_mode="file-media",
            resolution=(width, height),
            crop_padding=args.crop_padding,
            context={
                "backend": config.backend,
                "device": args.device,
                "input_size": config.input_size,
                "min_confidence": config.min_confidence,
                "alert_threshold": args.alert_threshold,
                "person_crop_enabled": config.person_crop_enabled,
                "policy_source": policy_source or "sc5-policy",
                "thresholds": {
                    "weapon_min_confidence": config.min_confidence,
                    "weapon_independent_alert_threshold": config.independent_alert_threshold,
                },
                "caller": "backend/tools/weapon_fp_log_run.py",
            },
            run_id=args.run_id,
            fixture_id=identity.get("fixture_id", f"unregistered:{path.stem}"),
            source_sha256=digest,
            split=identity.get("split", "unregistered"),
        )
        engine._fp_logger = logger
        if not engine._ensure_model_loaded():
            raise SystemExit(f"weapon model failed to load: {engine.status().get('reason')}")
        frames_seen = 0
        for index, time_s, frame in frames_from_clip(path, max(1, args.stride)):
            if args.max_frames and frames_seen >= args.max_frames:
                break
            engine._fp_logger = logger
            engine.predict_hits(frame, frame_index=index, time_s=time_s)
            frames_seen += 1
        summary = logger.summary()
        summary["frames_sampled"] = frames_seen
        summary["stride"] = max(1, args.stride)
        summary["model_sha256"] = getattr(engine._backend, "model_sha256", None)
        summary["execution_provider"] = getattr(engine._backend, "execution_provider", None)
        summary["health"] = engine.status()["health"]
        clip_summaries.append(summary)
        run_rows.extend(logger.rows)
        if args.wt12_outputs:
            record = wt12_output_record(
                fixture_id=logger.fixture_id, source_sha256=digest, run_id=args.run_id,
                rows=logger.rows, alert_threshold=args.alert_threshold)
            outputs_dir = Path(args.wt12_outputs)
            outputs_dir.mkdir(parents=True, exist_ok=True)
            (outputs_dir / f"{logger.fixture_id}.json").write_text(
                json.dumps(record, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    for row in run_rows:
        validate_fp_record(row)
    summary = summarize_negative_run(run_rows, alert_threshold=args.alert_threshold)
    summary.update({
        "run_id": args.run_id,
        "source_label": args.source_label,
        "clips": clip_summaries,
        "media": [str(path) for path in media],
    })
    report_path = out_root / f"negative_run_{args.run_id}.json"
    report_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clips", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-label", default=None)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--crop-padding", type=float, default=0.12,
                        help="evidence crop margin as a fraction of box size (10-15%%)")
    parser.add_argument("--alert-threshold", type=float, required=True,
                        help="alert operating point for the FP summary (SC-5 value)")
    parser.add_argument("--policy-json", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--fixture-filter", default=None,
                        help="only run manifest fixtures whose fixture_id contains this "
                             "substring (e.g. walking / waving / boxing); unregistered "
                             "media are excluded when this is set")
    parser.add_argument("--wt12-outputs", default=None,
                        help="also write WT-12 outputs schema records into this directory "
                             "(manifest-registered fixtures only)")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--min-confidence-override", type=float, default=None)
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps({
        "run_id": summary["run_id"],
        "denominators": summary["denominators"],
        "false_alert_frames": summary["false_alert_frames"],
        "detections_at_or_above_alert": summary["detections_at_or_above_alert"],
        "per_class": summary["per_class"],
        "splits": summary["splits"],
    }, indent=2))


if __name__ == "__main__":
    main()
