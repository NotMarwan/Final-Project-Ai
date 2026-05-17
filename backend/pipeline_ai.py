"""Dedicated AI inference thread — processes frames from queue, stores results.

This thread pops frames from the capture queue and runs all AI models:
- Violence detection (X3D, GPU/FP16)
- Weapon detection (YOLO, ONNX/GPU)
- Person detection (YOLO, ONNX/GPU)
- Motion estimation (frame diff)

Results are stored in a thread-safe OverlayCache for the render thread.
"""
from __future__ import annotations

import time
import threading
from collections import deque
from typing import Optional

import cv2
import numpy as np


def estimate_motion_score(
    previous_frame: Optional[np.ndarray],
    current_frame: np.ndarray,
) -> float:
    """Compute motion score between two frames (0.0 = still, 1.0 = high motion)."""
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


class AIThread:
    """Consumer thread: pops frames from queue, runs AI, stores results."""

    def __init__(
        self,
        frame_queue: deque,
        result_cache,  # OverlayCache instance
        pipeline,  # ViolenceInferencePipeline instance
        weapon_engine,  # WeaponSignalEngine instance
        person_detector,  # PersonDetector instance
        stop_event: threading.Event,
        violence_cls: int = 1,
    ):
        self.frame_queue = frame_queue
        self.result_cache = result_cache
        self.pipeline = pipeline
        self.weapon_engine = weapon_engine
        self.person_detector = person_detector
        self.stop_event = stop_event
        self.violence_cls = violence_cls
        self._previous_frame: Optional[np.ndarray] = None
        self.frame_count: int = 0
        self.inference_count: int = 0

    def run(self):
        """Main loop — runs until stop_event is set."""
        while not self.stop_event.is_set():
            if not self.frame_queue:
                time.sleep(0.01)
                continue

            try:
                frame = self.frame_queue.popleft()
            except IndexError:
                time.sleep(0.01)
                continue

            self._process_frame(frame)

    def _process_frame(self, frame: np.ndarray):
        """Run all AI models on a single frame."""
        self.frame_count += 1
        t0 = time.perf_counter()

        # 1. Violence detection (runs on stride interval internally)
        self.pipeline.process_frame(frame)

        # 2. Weapon detection (async internally)
        weapon_signal = self.weapon_engine.process_frame(frame)
        weapon_score = float(weapon_signal.get("score", 0.0))
        weapon_labels = list(weapon_signal.get("labels", []))

        # 3. Person detection
        tracks = []
        person_count = 0
        if self.person_detector is not None and self.person_detector.enabled:
            try:
                detections = self.person_detector.detect(frame)
                person_count = len(detections) if detections else 0
                tracks = detections if detections else []
            except Exception as exc:
                print(f"[AI] Person detection error: {exc}")

        # 4. Motion estimation
        motion_score = estimate_motion_score(self._previous_frame, frame)

        # 5. Read violence results
        violence_conf = float(getattr(self.pipeline, "_last_conf", 0.0))
        violence_is_threat = bool(
            self.pipeline.enabled
            and getattr(self.pipeline, "_last_label", None) == self.violence_cls
            and violence_conf > 0.3
        )
        weapon_is_threat = bool(weapon_score >= 0.30)
        is_threat = violence_is_threat or weapon_is_threat

        # 6. Store results in cache
        fused_threat_conf = max(violence_conf, weapon_score) * 100
        self.result_cache.update(
            tracks=tracks,
            person_count=person_count,
            is_threat=is_threat,
            threat_confidence=fused_threat_conf,
            weapon_score=weapon_score,
            weapon_labels=weapon_labels,
            violence_conf=violence_conf,
            violence_label="violence" if is_threat else "normal",
            motion_score=motion_score,
        )

        self._previous_frame = frame.copy()
        self.inference_count += 1

        latency_ms = (time.perf_counter() - t0) * 1000
        if self.inference_count % 10 == 0:
            print(f"[AI] Frame {self.frame_count}: {latency_ms:.1f}ms | "
                  f"violence={violence_conf:.2f} weapon={weapon_score:.2f} "
                  f"persons={person_count} motion={motion_score:.2f}")

    def get_stats(self) -> dict:
        """Return thread statistics."""
        return {
            "frame_count": self.frame_count,
            "inference_count": self.inference_count,
            "queue_size": len(self.frame_queue),
        }
