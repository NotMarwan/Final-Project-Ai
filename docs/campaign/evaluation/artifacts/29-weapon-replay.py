"""WT-29 P2.4 — weapon observation flow under paced replay (open-item resolution).

Paced replay of a REAL fixture (KTH, file-media) through the assembled candidate's
`backend.weapon.WeaponSignalEngine` with `weapon_config` DEFAULTS (no env overrides),
logging per-tick `latest_signal()` fields (reason / observation_id / observation_valid)
to resolve the WT-15 open item:

    "weapon observations unaccounted under paced replay with healthy engine status —
     cadence/validity gate suspected, unmeasured mechanism"

Mechanism discrimination in the output:
- completed observations = max(observation_id) reached (producer counter, SC-2)
- "harness accounting" variant A = ticks where observation_valid is True
- "harness accounting" variant B = ticks where observation_id CHANGED vs previous tick
- gate telemetry = skipped_frames (eligible but suppressed) + interval/cadence fields

Run (from wt-29 root, script-clock timestamps, RESOURCE-LOCK held by the caller):
    C:/Users/PCD/Downloads/Final Project AI Sentinel/venv/Scripts/python.exe ^
        docs/campaign/evaluation/artifacts/29-weapon-replay.py ^
        --fixture C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12-fixtures/kth/person01_boxing_d1_uncomp.avi ^
        --seconds 90 --out docs/campaign/evaluation/artifacts/29-weapon-replay.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--seconds", type=float, default=90.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--fps", type=float, default=25.0, help="paced replay rate (KTH = 25 fps)")
    args = ap.parse_args()

    started_wall = time.time()
    started_mono = time.monotonic()
    print(f"[29-replay] start wall={started_wall:.3f} mono={started_mono:.3f}", flush=True)

    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415
    from weapon import WeaponConfig, WeaponSignalEngine  # noqa: PLC0415

    # weapon_config DEFAULTS: empty settings + empty env => SC-5 policy defaults.
    cfg = WeaponConfig.from_settings({}, {})
    print(f"[29-replay] config: backend={cfg.backend} interval={cfg.interval} "
          f"min_interval_ms={cfg.min_interval_ms} signal_ttl_ms={cfg.signal_ttl_ms} "
          f"min_confidence={cfg.min_confidence} weight_path={cfg.weight_path}", flush=True)

    engine = WeaponSignalEngine.from_settings({}, {})
    cap = cv2.VideoCapture(args.fixture)
    if not cap.isOpened():
        print(f"[29-replay] FAIL cannot open fixture {args.fixture}", flush=True)
        return 2
    frames: list = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    src_fps = cv2.VideoCapture(args.fixture).get(cv2.CAP_PROP_FPS) or args.fps
    print(f"[29-replay] fixture={args.fixture} frames={len(frames)} fps={src_fps}", flush=True)
    if not frames:
        print("[29-replay] FAIL empty fixture", flush=True)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tick = 0
    prev_obs = -1
    valid_ticks = 0
    changed_ticks = 0
    reasons: dict[str, int] = {}
    obs_history: list[int] = []
    first_completed_after: float | None = None
    deadline = started_mono + args.seconds
    frame_dt = 1.0 / args.fps

    with out_path.open("w", encoding="utf-8") as fh:
        while time.monotonic() < deadline:
            frame = frames[tick % len(frames)]
            observed_at = time.monotonic()
            engine.process_frame(np.ascontiguousarray(frame), observed_at=observed_at)
            sig = engine.latest_signal()
            obs = int(sig.get("observation_id", 0))
            reason = str(sig.get("reason", ""))
            valid = bool(sig.get("observation_valid"))
            reasons[reason] = reasons.get(reason, 0) + 1
            if valid:
                valid_ticks += 1
            if obs != prev_obs:
                changed_ticks += 1
                if obs > 0 and first_completed_after is None:
                    first_completed_after = observed_at - started_mono
            if obs > 0 and (not obs_history or obs_history[-1] != obs):
                obs_history.append(obs)
            fh.write(json.dumps({
                "tick": tick,
                "mono": round(observed_at - started_mono, 4),
                "observation_id": obs,
                "reason": reason,
                "observation_valid": valid,
                "score": sig.get("score"),
                "inferenceRunning": sig.get("inferenceRunning"),
            }) + "\n")
            prev_obs = obs
            tick += 1
            target = started_mono + tick * frame_dt
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)

    end_mono = time.monotonic()
    final = engine.latest_signal()
    engine.close()
    summary = {
        "fixture": args.fixture,
        "paced_fps": args.fps,
        "requested_seconds": args.seconds,
        "ticks": tick,
        "wall_seconds": round(end_mono - started_mono, 3),
        "completed_observations_max_id": int(final.get("observation_id", 0)),
        "completed_observation_ids_seen": obs_history,
        "first_completed_observation_after_s": first_completed_after,
        "valid_ticks": valid_ticks,
        "changed_ticks": changed_ticks,
        "reasons": reasons,
        "final_signal": {k: final.get(k) for k in (
            "observation_id", "reason", "observation_valid", "score",
            "skippedFrames", "minIntervalMs", "inferenceRunning", "failed", "ready")},
    }
    (out_path.parent / (out_path.stem + "-summary.json")).write_text(
        json.dumps(summary, indent=1), encoding="utf-8")
    print("[29-replay] SUMMARY " + json.dumps(summary), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
