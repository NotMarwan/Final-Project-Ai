"""Inference subprocess — loads all AI models in a separate process.

Runs violence detection, weapon detection, person detection, and motion
estimation in a dedicated process that owns its own CUDA context. This
bypasses the Python GIL and prevents AI inference from blocking the
capture/render pipeline.

Communication:
  - Receives numpy frames via multiprocessing.Queue (frame_queue)
  - Pushes result dicts via multiprocessing.Queue (result_queue)
  - Stops via multiprocessing.Event (stop_event)
"""
from __future__ import annotations

import time
import multiprocessing as mp
from collections import deque
from queue import Empty
from typing import Optional

import cv2
import numpy as np


MOTION_GATE_THRESHOLD = 0.0


def default_result() -> dict:
    """Return a default empty result dict."""
    return {
        "is_threat": False,
        "threat_confidence": 0.0,
        "violence_conf": 0.0,
        "weapon_score": 0.0,
        "weapon_labels": [],
        "weapon_bbox": None,
        "violence_bbox": None,
        "person_count": 0,
        "tracks": [],
        "motion_score": 0.0,
        "fps": 0.0,
        "video_width": 0,
        "video_height": 0,
        "frame_idx": 0,
        "timestamp": 0.0,
    }


def estimate_motion_score(
    previous_frame: Optional[np.ndarray],
    current_frame: np.ndarray,
) -> float:
    if previous_frame is None:
        return 0.0
    try:
        prev_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
        prev_small = cv2.resize(prev_gray, (64, 64), interpolation=cv2.INTER_AREA)
        curr_small = cv2.resize(curr_gray, (64, 64), interpolation=cv2.INTER_AREA)
        diff = cv2.absdiff(prev_small, curr_small)
        return float(diff.mean() / 255.0)
    except Exception:
        return 0.0


def _normalize_bbox(raw_bbox) -> Optional[list[float]]:
    if raw_bbox and isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
        try:
            return [float(v) for v in raw_bbox]
        except (TypeError, ValueError):
            return None
    return None


def read_weapon_signal(weapon_engine, frame: np.ndarray) -> tuple[float, list[str], Optional[list[float]]]:
    """Read the latest weapon signal without zeroing it between inference ticks."""
    if weapon_engine is None:
        return 0.0, [], None

    signal = None
    try:
        signal = weapon_engine.process_frame(frame)
    except Exception:
        signal = None

    if not signal:
        try:
            signal = weapon_engine.latest_signal()
        except Exception:
            signal = None

    if not signal:
        return 0.0, [], None

    return (
        float(signal.get("score", 0.0)),
        list(signal.get("labels", [])),
        _normalize_bbox(signal.get("bbox")),
    )


def read_violence_signal(violence_pipeline, frame: np.ndarray) -> tuple[float, int]:
    """Trigger violence inference and return the latest completed async result."""
    if violence_pipeline is None or not getattr(violence_pipeline, "enabled", False):
        return 0.0, 0

    try:
        violence_pipeline.process_frame(frame)
    except Exception:
        return 0.0, 0

    state_lock = getattr(violence_pipeline, "_state_lock", None)
    if state_lock is None:
        return (
            float(getattr(violence_pipeline, "_last_conf", 0.0)),
            int(getattr(violence_pipeline, "_last_label", 0)),
        )

    with state_lock:
        return (
            float(getattr(violence_pipeline, "_last_conf", 0.0)),
            int(getattr(violence_pipeline, "_last_label", 0)),
        )


def inference_worker(
    frame_queue: mp.Queue,
    result_queue: mp.Queue,
    stop_event: mp.Event,
    config: dict,
):
    """Entry point for the inference subprocess.

    Args:
        frame_queue: receives numpy frames from capture thread
        result_queue: sends result dicts back to main process
        stop_event: signals shutdown
        config: dict with model paths, device, strides, etc.
    """
    import torch
    import sys
    import os

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    device_str = config.get("device", "cuda")
    device = torch.device(device_str if torch.cuda.is_available() and device_str.startswith("cuda") else "cpu")
    weights_path = config.get("weights_path", "best_model.pt")
    weapon_path = config.get("weapon_path", "weapon_yolo.pt")
    violence_stride = config.get("violence_stride", 8)
    person_interval = config.get("person_interval", 3)
    weapon_config_dict = config.get("weapon_config", {})
    person_conf = config.get("person_conf_threshold", 0.45)
    weapon_min_confidence = config.get("weapon_min_confidence", 0.20)

    print(f"[InferenceProc] Starting on device={device}")

    # ── Load Violence Model ──
    try:
        from inference import ViolenceInferencePipeline, VIOLENCE_CLS
        violence_pipeline = ViolenceInferencePipeline(
            weights_path=weights_path,
            device=device,
            threshold=config.get("threshold", 0.65),
            stride=violence_stride,
        )
        print(f"[InferenceProc] Violence model loaded. enabled={violence_pipeline.enabled} cls={VIOLENCE_CLS}")
    except Exception as exc:
        print(f"[InferenceProc] Violence model FAILED: {exc}")
        violence_pipeline = None
        VIOLENCE_CLS = 1

    # ── Load Weapon Model ──
    weapon_engine = None
    try:
        from weapon import WeaponSignalEngine, WeaponConfig
        w_cfg = WeaponConfig.from_settings(weapon_config_dict)
        weapon_engine = WeaponSignalEngine(config=w_cfg, device=device)
        if weapon_engine.enabled:
            weapon_engine.preload()
            print(f"[InferenceProc] Weapon engine ready.")
        else:
            print(f"[InferenceProc] Weapon engine disabled.")
            weapon_engine = None
    except Exception as exc:
        print(f"[InferenceProc] Weapon engine FAILED: {exc}")

    # ── Load Person Detector ──
    person_detector = None
    if config.get("person_overlay_enabled", True):
        try:
            from person_detector import PersonDetector
            person_detector = PersonDetector(conf_threshold=person_conf, device=device.type)
            print(f"[InferenceProc] Person detector initialized.")
        except Exception as exc:
            print(f"[InferenceProc] Person detector FAILED: {exc}")
    else:
        print(f"[InferenceProc] Person detector disabled via config.")

    # ── CUDA stream for overlapping weapon + person ──
    weapon_stream = None
    if device.type == "cuda":
        try:
            weapon_stream = torch.cuda.Stream(device=device)
        except Exception:
            weapon_stream = None

    # ── Main loop ──
    buffer = deque(maxlen=32)
    prev_frame: Optional[np.ndarray] = None
    frame_idx = 0
    _first_frame = True
    cached = default_result()
    violence_cls = VIOLENCE_CLS if violence_pipeline is not None else 1
    last_tracks: list[dict] = []
    last_person_count = 0

    print(f"[InferenceProc] Entering main loop.")

    while not stop_event.is_set():
        try:
            frame = frame_queue.get(timeout=0.05)
        except Empty:
            continue

        frame_idx += 1
        t0 = time.perf_counter()

        # ── 1. Motion estimation (every frame, fast) ──
        motion = estimate_motion_score(prev_frame, frame)
        prev_frame = frame

        # Motion gate: skip AI on still frames (always process first frame)
        if not _first_frame and motion < MOTION_GATE_THRESHOLD:
            result = dict(cached)
            result["motion_score"] = motion
            result["frame_idx"] = frame_idx
            result["timestamp"] = time.time()
            result_queue.put(result, timeout=0.1)
            continue
        _first_frame = False

        # ── 2. Violence detection (stride) ──
        violence_conf = 0.0
        violence_is_violence = 0
        if violence_pipeline is not None and violence_pipeline.enabled:
            violence_conf, violence_is_violence = read_violence_signal(violence_pipeline, frame)

        # ── 3. Weapon detection (interval) ──
        weapon_score, weapon_labels, weapon_bbox = read_weapon_signal(weapon_engine, frame)

        # ── 4. Person detection (interval) ──
        tracks = [dict(track) for track in last_tracks]
        person_count = int(last_person_count)
        if person_detector is not None and person_detector.enabled and frame_idx % person_interval == 0:
            try:
                detections = person_detector.detect(frame)
                person_count = len(detections) if detections else 0
                tracks = detections if detections else []
                last_person_count = person_count
                last_tracks = [dict(track) for track in tracks]
            except Exception as exc:
                print(f"[InferenceProc] Person detection error: {exc}")

        # ── 5. Fuse results ──
        violence_is_threat = bool(
            violence_pipeline is not None
            and violence_pipeline.enabled
            and violence_is_violence == violence_cls
            and violence_conf > 0.25
        )
        weapon_is_threat = bool(weapon_score >= 0.40)
        is_threat = violence_is_threat or weapon_is_threat
        fused_threat_conf = max(violence_conf, weapon_score) * 100

        # Compute violence bbox from person tracks or full frame
        violence_bbox = None
        if violence_is_threat:
            if tracks:
                # Use largest person track bbox as violence region
                best_track = max(tracks, key=lambda t: (t.get("bbox", [0, 0, 0, 0])[2] - t.get("bbox", [0, 0, 0, 0])[0]) * (t.get("bbox", [0, 0, 0, 0])[3] - t.get("bbox", [0, 0, 0, 0])[1]))
                violence_bbox = best_track.get("bbox")
            if violence_bbox is None and frame is not None:
                # Fallback: full frame (normalized 0-1)
                violence_bbox = [0.05, 0.05, 0.95, 0.95]

        result = {
            "is_threat": is_threat,
            "threat_confidence": fused_threat_conf,
            "violence_conf": violence_conf,
            "weapon_score": weapon_score,
            "weapon_labels": weapon_labels,
            "weapon_bbox": weapon_bbox,
            "violence_bbox": violence_bbox if violence_is_threat else None,
            "person_count": person_count,
            "tracks": tracks,
            "motion_score": motion,
            "fps": 0.0,
            "video_width": int(frame.shape[1]) if frame is not None else 0,
            "video_height": int(frame.shape[0]) if frame is not None else 0,
            "frame_idx": frame_idx,
            "timestamp": time.time(),
        }
        cached = dict(result)

        result_queue.put(result, timeout=0.1)

        latency = (time.perf_counter() - t0) * 1000
        if frame_idx % 10 == 0:
            print(f"[InferenceProc] Frame {frame_idx}: {latency:.1f}ms | "
                  f"violence={violence_conf:.2f} weapon={weapon_score:.2f} "
                  f"persons={person_count} motion={motion:.2f}")

    print("[InferenceProc] Shutting down.")
