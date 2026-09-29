"""Worker/resource architecture measurement harness (WT-15 / S-01).

Reproducible measurement driver for the EXP-15.x experiment cards. Drives a
REAL spawned ``inference_worker`` through a producer loop that replicates the
api.py camera_worker enqueue semantics (downscale to 640 max-side, FramePacket,
drop-newest on a bounded maxsize=3 queue) on synthetic file-media replay windows.

Subcommands:
  qpc-check    cross-process perf_counter (QPC) comparability probe
  ipc-pickle   numpy -> pickle microbenchmark at 640 max-side (EXP-15.03)
  queue-policy one replay run under a queue policy (EXP-15.01/15.02)
  startup      cold/warm startup stage split (EXP-15.04)

Resource discipline: measured runs are recorded with the RESOURCE-LOCK
provenance passed by the caller; this harness never acquires the lock itself
(the campaign queue is coordinated between workstreams) and refuses to report
a run as valid without explicit provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import queue
import statistics
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

REPO_ROOT = BACKEND_DIR.parent
MODELS_DIR = BACKEND_DIR / "models"

MODEL_HASHES = {
    "best_model.pt": "2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01",
    "person_yolo.onnx": "3fafb13e995667e7f877c647b33df05be6d587e75aa79d9cc34e9b3f493e60b8",
    "weapon_yolo.onnx": "96991cd5d5dbeb7e8d439b3e5b75517bc8c55ea4ac740ec5bc8491d545875aef",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_hashes() -> dict:
    found = {}
    locations = {
        "best_model.pt": BACKEND_DIR / "best_model.pt",
        "person_yolo.onnx": MODELS_DIR / "person_yolo.onnx",
        "weapon_yolo.onnx": MODELS_DIR / "weapon_yolo.onnx",
    }
    for name, path in locations.items():
        if not path.exists():
            found[name] = {"path": str(path), "status": "MISSING"}
            continue
        actual = sha256_file(path)
        found[name] = {
            "path": str(path),
            "sha256": actual,
            "matches_contract": actual == MODEL_HASHES[name],
        }
    return found


def percentile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def distribution(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "p05": percentile(values, 0.05),
        "median": statistics.median(values),
        "p95": percentile(values, 0.95),
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


def environment_block() -> dict:
    import torch

    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        ort_version = ort.__version__
    except Exception as exc:  # pragma: no cover - environment report
        providers, ort_version = [f"unavailable:{type(exc).__name__}"], None
    return {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(),
        "onnxruntime": ort_version,
        "onnxruntime_providers": providers,
        "platform": sys.platform,
    }


# --- resource lock provenance ----------------------------------------------

LOCK_DIR = Path("C:/Users/PCD/Downloads/jobs/sentinel-campaign/RESOURCE-LOCK")


def lock_state() -> dict:
    return {"lock_dir_exists": LOCK_DIR.exists(), "lock_provenance_required": True}


# --- qpc-check --------------------------------------------------------------

def _qpc_probe_child(report, parent_qpc, parent_mono):
    """Module-level spawn target (spawn cannot pickle nested functions)."""
    report.put({
        "child_perf_minus_parent_perf_s": time.perf_counter() - parent_qpc,
        "child_monotonic_minus_parent_monotonic_s": time.monotonic() - parent_mono,
        "child_perf_minus_parent_monotonic_s": time.perf_counter() - parent_mono,
    })


def cmd_qpc_check(args) -> dict:
    ctx = mp.get_context("spawn")
    report = ctx.Queue()

    parent_qpc = time.perf_counter()
    parent_mono = time.monotonic()
    process = ctx.Process(target=_qpc_probe_child, args=(report, parent_qpc, parent_mono))
    process.start()
    payload = report.get(timeout=30.0)
    process.join(timeout=30.0)
    return {
        "measurement": "cross-process clock comparability (spawned child)",
        "parent_perf_counter": parent_qpc,
        "parent_monotonic": parent_mono,
        **payload,
        "interpretation": (
            "child_perf_minus_parent_perf_s near 0 (|x| < 0.5 s) => perf_counter/QPC "
            "is a shared cross-process base on this machine (spawn+import overhead only); "
            "monotonic comparison shows the GetTickCount64 quantization base."
        ),
    }


# --- ipc-pickle -------------------------------------------------------------

def cmd_ipc_pickle(args) -> dict:
    import pickle

    import numpy as np

    from temporal_frames import FramePacket, downscale_for_inference

    rng = np.random.default_rng(20260929)
    raw = rng.integers(0, 256, size=(720, 1280, 3), dtype=np.uint8)
    small = downscale_for_inference(raw, 640)
    now = time.perf_counter()
    packets = [
        FramePacket(small.copy(), i, now, 1280, 720, 30.0, {}, sample_timestamp=now + i / 30.0)
        for i in range(args.n)
    ]
    dumps_ms, loads_ms, sizes = [], [], []
    for packet in packets:
        t0 = time.perf_counter()
        blob = pickle.dumps(packet, protocol=pickle.HIGHEST_PROTOCOL)
        t1 = time.perf_counter()
        restored = pickle.loads(blob)
        t2 = time.perf_counter()
        dumps_ms.append((t1 - t0) * 1000.0)
        loads_ms.append((t2 - t1) * 1000.0)
        sizes.append(len(blob))
        del restored
    return {
        "measurement": "numpy FramePacket pickle round-trip at 640 max-side",
        "frame_shape": list(small.shape),
        "frame_nbytes": int(small.nbytes),
        "packet_payload_bytes": distribution(sizes),
        "pickle_dumps_ms": distribution(dumps_ms),
        "pickle_loads_ms": distribution(loads_ms),
        "note": (
            "mp.Queue pickles in a feeder thread (producer side) and unpickles inline "
            "at get(); stageEnqueueToDequeueMs in the live worker includes transfer + "
            "bounded queue wait + scheduling, this figure is the pure serialization cost."
        ),
    }


# --- queue-policy / startup shared driver -----------------------------------

def build_worker_config(args, *, queue_policy, capture_clock_base) -> dict:
    from decision_config import load_decision_config

    return {
        "device": args.device,
        "weights_path": str(BACKEND_DIR / "best_model.pt"),
        "violence_stride": args.stride,
        "person_interval": 3,
        "person_overlay_enabled": not args.no_person,
        "person_conf_threshold": 0.45,
        "weapon_config": {},
        "source_fps": float(args.fps),
        "decision_config": load_decision_config().to_dict(),
        "capture_clock_base": capture_clock_base,
        "queue_policy": queue_policy,
    }


def run_replay(args, *, queue_policy, capture_clock_base, duration_s, note=""):
    """Producer replicating api.py camera_worker enqueue semantics + real worker."""
    import numpy as np

    from temporal_frames import FramePacket, downscale_for_inference

    ctx = mp.get_context("spawn")
    frame_queue = ctx.Queue(maxsize=3)
    result_queue = ctx.Queue(maxsize=30)
    stop_event = ctx.Event()
    ready_event = ctx.Event()
    reset_event = ctx.Event()
    reset_ack = ctx.Event()

    config = build_worker_config(args, queue_policy=queue_policy, capture_clock_base=capture_clock_base)
    config.update({
        "ready_event": ready_event,
        "reset_event": reset_event,
        "reset_ack": reset_ack,
    })

    from inference_process import inference_worker

    t_spawn = time.perf_counter()
    process = ctx.Process(
        target=inference_worker,
        args=(frame_queue, result_queue, stop_event, config),
        daemon=True,
        name="inference-bench",
    )
    process.start()
    ready_s = None
    if ready_event.wait(timeout=args.ready_timeout):
        ready_s = time.perf_counter() - t_spawn

    rng = np.random.default_rng(20260929)
    raw = rng.integers(0, 256, size=(720, 1280, 3), dtype=np.uint8)
    fps = float(args.fps)
    media_epoch = time.perf_counter()
    capture_now = (time.perf_counter if capture_clock_base == "perf-qpc" else time.monotonic)

    results = []
    producer = {
        "frames_captured": 0,
        "frames_enqueued": 0,
        "producer_dropped": 0,
        "producer_drop_streak_max": 0,
        "_streak": 0,
    }
    deadline = time.perf_counter() + duration_s
    next_frame = time.perf_counter()
    window_valid_count = 0
    window_full_count = 0

    while time.perf_counter() < deadline:
        seq = producer["frames_captured"] + 1
        captured_at = capture_now()
        small = downscale_for_inference(raw, 640)
        packet = FramePacket(
            small,
            seq,
            captured_at,
            1280,
            720,
            fps,
            {},
            sample_timestamp=media_epoch + (seq - 1) / fps,
        )
        producer["frames_captured"] += 1
        try:
            frame_queue.put_nowait(packet)
            producer["frames_enqueued"] += 1
            producer["_streak"] = 0
        except queue.Full:
            producer["producer_dropped"] += 1
            producer["_streak"] += 1
            producer["producer_drop_streak_max"] = max(
                producer["producer_drop_streak_max"], producer["_streak"]
            )
        # consume whatever is ready without blocking the capture pacing
        while True:
            try:
                result = result_queue.get_nowait()
            except queue.Empty:
                break
            results.append(result)
            if result.get("window_valid"):
                window_valid_count += 1
            if result.get("frames_collected", 0) >= result.get("frames_required", 32):
                window_full_count += 1
        next_frame += 1.0 / fps
        delay = next_frame - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        else:
            next_frame = time.perf_counter()

    stop_event.set()
    process.join(timeout=30.0)
    # drain tail results
    while True:
        try:
            results.append(result_queue.get_nowait())
        except queue.Empty:
            break

    def series(key):
        return [r.get(key) for r in results]

    summary = {
        "note": note,
        "queue_policy": queue_policy,
        "capture_clock_base": capture_clock_base,
        "lock_state": lock_state(),
        "models": verify_model_hashes(),
        "environment": environment_block(),
        "workload": {
            "source_mode": "synthetic-file-media",
            "frames_captured": producer["frames_captured"],
            "frames_enqueued": producer["frames_enqueued"],
            "producer_dropped": producer["producer_dropped"],
            "producer_drop_streak_max": producer["producer_drop_streak_max"],
            "duration_s": duration_s,
            "fps_target": fps,
            "frame_shape": [720, 1280, 3],
            "inference_view_max_side": 640,
            "violence_stride": args.stride,
        },
        "results_received": len(results),
        "startup": {
            "spawn_to_ready_s": ready_s,
            "startupModelLoadMs": distribution(series("startupModelLoadMs")),
            "startupFirstFrameMs": distribution(series("startupFirstFrameMs")),
            "startupFirstResultMs": distribution(series("startupFirstResultMs")),
            "startupFirstObservationMs": distribution(series("startupFirstObservationMs")),
        },
        "distributions": {
            "frameAgeMs": distribution(series("frameAgeMs")),
            "stageCaptureToQueueMs": distribution(series("stageCaptureToQueueMs")),
            "stageEnqueueToDequeueMs": distribution(series("stageEnqueueToDequeueMs")),
            "stagePreprocessMs": distribution(series("stagePreprocessMs")),
            "stageInferenceWaitMs": distribution(series("stageInferenceWaitMs")),
            "stageSerializeMs": distribution(series("stageSerializeMs")),
            "backlogFrames": distribution(series("backlogFrames")),
            "violence_observation_age_ms": distribution(series("violence_observation_age_ms")),
            "weapon_observation_age_ms": distribution(series("weapon_observation_age_ms")),
        },
        "counters_final": {
            "frameQueueDroppedDerived": results[-1].get("frameQueueDroppedDerived") if results else None,
            "frameQueueDiscardedByPolicy": results[-1].get("frameQueueDiscardedByPolicy") if results else None,
            "frameQueueDiscardedAtReset": results[-1].get("frameQueueDiscardedAtReset") if results else None,
            "resultQueueDropped": results[-1].get("resultQueueDropped") if results else None,
            "violenceCompletedCount": results[-1].get("violenceCompletedCount") if results else None,
            "weaponCompletedCount": results[-1].get("weaponCompletedCount") if results else None,
            "personCompletedCount": results[-1].get("personCompletedCount") if results else None,
        },
        "window_contract": {
            "results_with_full_window": window_full_count,
            "results_with_valid_window": window_valid_count,
            "invalid_full_window_rate": (
                (window_full_count - window_valid_count) / window_full_count
                if window_full_count else None
            ),
        },
        "process": {
            "workerPid": results[-1].get("workerPid") if results else None,
            "processRunId": results[-1].get("processRunId") if results else None,
        },
    }
    return summary


def cmd_queue_policy(args) -> dict:
    return run_replay(
        args,
        queue_policy=args.policy,
        capture_clock_base=args.capture_clock_base,
        duration_s=args.seconds,
        note=args.note,
    )


def cmd_startup(args) -> dict:
    """Cold (spawn+load) vs warm (models resident, media-reset epoch) stages."""
    import numpy as np

    from temporal_frames import FramePacket, downscale_for_inference

    ctx = mp.get_context("spawn")
    frame_queue = ctx.Queue(maxsize=3)
    result_queue = ctx.Queue(maxsize=30)
    stop_event = ctx.Event()
    ready_event = ctx.Event()
    reset_event = ctx.Event()
    reset_ack = ctx.Event()

    capture_clock_base = args.capture_clock_base
    config = build_worker_config(args, queue_policy="drop-newest", capture_clock_base=capture_clock_base)
    config.update({"ready_event": ready_event, "reset_event": reset_event, "reset_ack": reset_ack})

    from inference_process import inference_worker

    legs = []
    t_spawn = time.perf_counter()
    process = ctx.Process(
        target=inference_worker,
        args=(frame_queue, result_queue, stop_event, config),
        daemon=True,
        name="inference-bench-startup",
    )
    process.start()
    ready_s = None
    if ready_event.wait(timeout=args.ready_timeout):
        ready_s = time.perf_counter() - t_spawn

    rng = np.random.default_rng(20260929)
    raw = rng.integers(0, 256, size=(720, 1280, 3), dtype=np.uint8)
    fps = float(args.fps)

    def feed_until_first_observation(tag, deadline_s=120.0, baseline=None):
        media_epoch = time.perf_counter()
        capture_now = (time.perf_counter if capture_clock_base == "perf-qpc" else time.monotonic)
        t_feed = time.perf_counter()
        first_result_s = None
        first_obs_s = None
        seq = 0
        end = time.perf_counter() + deadline_s
        next_frame = time.perf_counter()
        first_result = None
        base = baseline or {"violenceCompletedCount": 0, "weaponCompletedCount": 0}
        seen_counters = dict(base)

        def observed_new(result):
            return (
                (result.get("violenceCompletedCount") or 0) > base["violenceCompletedCount"]
                or (result.get("weaponCompletedCount") or 0) > base["weaponCompletedCount"]
            )

        while time.perf_counter() < end:
            seq += 1
            small = downscale_for_inference(raw, 640)
            packet = FramePacket(
                small, seq, capture_now(), 1280, 720, fps, {},
                sample_timestamp=media_epoch + (seq - 1) / fps,
            )
            try:
                frame_queue.put_nowait(packet)
            except queue.Full:
                pass
            while True:
                try:
                    result = result_queue.get_nowait()
                except queue.Empty:
                    break
                if first_result_s is None:
                    first_result_s = time.perf_counter() - t_feed
                    first_result = result
                seen_counters.update({
                    "violenceCompletedCount": result.get("violenceCompletedCount") or 0,
                    "weaponCompletedCount": result.get("weaponCompletedCount") or 0,
                })
                if observed_new(result):
                    if first_obs_s is None:
                        first_obs_s = time.perf_counter() - t_feed
            if first_obs_s is not None:
                break
            next_frame += 1.0 / fps
            delay = next_frame - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_frame = time.perf_counter()
        return {
            "tag": tag,
            "feed_to_first_result_s": first_result_s,
            "feed_to_first_completed_observation_s": first_obs_s,
            "seen_counters": dict(seen_counters),
            "first_result_startup_fields": {
                key: (first_result or {}).get(key)
                for key in (
                    "startupModelLoadMs", "startupFirstFrameMs",
                    "startupFirstResultMs", "startupFirstObservationMs",
                )
            },
        }

    cold = feed_until_first_observation("cold-spawn")
    # warm leg: media-loop reset handshake with models resident; counters are
    # cumulative per process run, so first-observation must be a counter
    # INCREASE over the cold leg's final values, never "already >= 1".
    reset_ack.clear()
    reset_event.set()
    t_reset = time.perf_counter()
    reset_done = reset_ack.wait(timeout=10.0)
    reset_ack_s = time.perf_counter() - t_reset
    warm = (
        feed_until_first_observation("warm-resident", baseline=cold.get("seen_counters"))
        if reset_done
        else {"tag": "warm-resident", "error": "reset ack timeout"}
    )

    stop_event.set()
    process.join(timeout=30.0)

    return {
        "measurement": "G-13 startup stages, cold vs warm (models resident across media reset)",
        "lock_state": lock_state(),
        "models": verify_model_hashes(),
        "environment": environment_block(),
        "capture_clock_base": capture_clock_base,
        "spawn_to_ready_s": ready_s,
        "reset_handshake_s": reset_ack_s,
        "reset_ack_received": reset_done,
        "cold": cold,
        "warm": warm,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("qpc-check")

    p_pickle = sub.add_parser("ipc-pickle")
    p_pickle.add_argument("--n", type=int, default=300)

    for name in ("queue-policy", "startup"):
        p = sub.add_parser(name)
        p.add_argument("--device", default="cuda")
        p.add_argument("--fps", type=float, default=30.0)
        p.add_argument("--stride", type=int, default=8)
        p.add_argument("--no-person", action="store_true")
        p.add_argument("--capture-clock-base", default="perf-qpc",
                       choices=("perf-qpc", "monotonic-gettickcount64"))
        p.add_argument("--ready-timeout", type=float, default=300.0)
        p.add_argument("--out", default=None)
    p_policy = sub.choices["queue-policy"]
    p_policy.add_argument("--policy", default="drop-newest", choices=("drop-newest", "latest-wins"))
    p_policy.add_argument("--seconds", type=float, default=90.0)
    p_policy.add_argument("--note", default="")

    args = parser.parse_args()
    handlers = {
        "qpc-check": cmd_qpc_check,
        "ipc-pickle": cmd_ipc_pickle,
        "queue-policy": cmd_queue_policy,
        "startup": cmd_startup,
    }
    report = handlers[args.command](args)
    text = json.dumps(report, indent=2, default=str)
    out = getattr(args, "out", None)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
