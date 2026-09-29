"""Thread-safe overlay cache for async AI results.

Decouples the main capture/stream loop from AI inference by storing
the latest detection results in a lock-free-ish cache. The main loop
reads from this cache and never waits for inference.
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from collections import deque
from typing import Optional
import numpy as np


@dataclass
class OverlayCache:
    """Thread-safe holder for the latest AI detection results.

    The main capture loop writes the latest frame; the AI worker writes
    overlay metadata.  The stream loop reads both independently.
    """
    tracks: list = field(default_factory=list)
    person_count: int = 0
    is_threat: bool = False
    threat_confidence: float = 0.0
    weapon_score: float = 0.0
    weapon_labels: list[str] = field(default_factory=list)
    fps: float = 0.0
    last_update: float = 0.0
    # Canonical counting semantics (S-04/WT-22); person_count stays as the
    # documented alias of active_track_count.
    visible_person_count: int = 0
    active_track_count: int = 0
    unique_person_estimate_window: Optional[dict] = None
    track_failure_flags: dict = field(default_factory=dict)
    person_tracker: str = ""
    # Extended fields for parallel pipeline
    violence_conf: float = 0.0
    violence_label: str = ""
    motion_score: float = 0.0
    video_width: int = 0
    video_height: int = 0
    # Additive tracker telemetry (WT-22); absent keys never overwrite.
    visible_person_count: int = 0
    active_track_count: int = 0
    unique_person_estimate_window: dict = field(default_factory=dict)
    track_failure_flags: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k) and k != "_lock":
                    setattr(self, k, v)
            self.last_update = time.time()

    def update_from_result(self, result: dict):
        """Merge an inference result dict from the subprocess into this cache."""
        mapping = {
            "is_threat": "is_threat",
            "threat_confidence": "threat_confidence",
            "weapon_score": "weapon_score",
            "weapon_labels": "weapon_labels",
            "person_count": "person_count",
            "tracks": "tracks",
            "visible_person_count": "visible_person_count",
            "active_track_count": "active_track_count",
            "unique_person_estimate_window": "unique_person_estimate_window",
            "track_failure_flags": "track_failure_flags",
            "person_tracker": "person_tracker",
            "violence_conf": "violence_conf",
            "motion_score": "motion_score",
            "visible_person_count": "visible_person_count",
            "active_track_count": "active_track_count",
            "unique_person_estimate_window": "unique_person_estimate_window",
            "track_failure_flags": "track_failure_flags",
        }
        with self._lock:
            for src_key, dst_key in mapping.items():
                if src_key in result:
                    setattr(self, dst_key, result[src_key])
            if "fps" in result and result["fps"] > 0:
                self.fps = result["fps"]
            if "video_width" in result and result["video_width"] > 0:
                self.video_width = result["video_width"]
            if "video_height" in result and result["video_height"] > 0:
                self.video_height = result["video_height"]
            self.last_update = time.time()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "tracks": list(self.tracks),
                "person_count": self.person_count,
                "visible_person_count": self.visible_person_count,
                "active_track_count": self.active_track_count,
                "unique_person_estimate_window": dict(self.unique_person_estimate_window or {}) or None,
                "track_failure_flags": dict(self.track_failure_flags),
                "person_tracker": self.person_tracker,
                "is_threat": self.is_threat,
                "threat_confidence": self.threat_confidence,
                "weapon_score": self.weapon_score,
                "weapon_labels": list(self.weapon_labels),
                "fps": self.fps,
                "last_update": self.last_update,
                "violence_conf": self.violence_conf,
                "violence_label": self.violence_label,
                "motion_score": self.motion_score,
                "video_width": self.video_width,
                "video_height": self.video_height,
            }


@dataclass
class FrameRingBuffer:
    """Small ring buffer of recent raw frames for evidence clips."""
    _buffer: deque = field(default_factory=lambda: deque(maxlen=140))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def push(self, frame: np.ndarray):
        with self._lock:
            self._buffer.append(frame)

    def snapshot(self) -> list[np.ndarray]:
        with self._lock:
            return list(self._buffer)

    def clear(self):
        with self._lock:
            self._buffer.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)


# --- multi-camera allocation rule (R-01, EXP-15.05) --------------------------
# Measured inputs live in docs/campaign/experiments/15-05-multicamera-vram.md;
# the constants below are the DECISION RULE and stay deterministic so the
# simulation test can pin them without a GPU.

POOLING_TRIGGER_CAMERAS = 3


def plan_inference_allocation(
    camera_count: int,
    vram_budget_gb: float = 12.0,
    per_camera_process_vram_gb: float | None = None,
    per_camera_pooled_vram_gb: float | None = None,
) -> dict:
    """Allocation rule for N cameras on one GPU.

    1-2 active cameras: one dedicated inference process per source (CUDA
    context isolation; measured VRAM per process at 1 and 2 workers feeds
    ``per_camera_process_vram_gb``).

    >= POOLING_TRIGGER_CAMERAS active cameras: the violence model (the large
    temporal checkpoint) moves to a pooled shared worker; weapon/person stay
    per camera. R-01: pool the violence model before exceeding the 12 GB
    ceiling once per-camera CUDA contexts (~0.5-1.5 GB each) plus model
    residency no longer fit.

    Unmeasured VRAM inputs must be passed as None (never guessed): the plan
    then reports ``estimated_vram_gb: None`` and sets ``unmeasured`` flags.
    """
    if camera_count < 1:
        raise ValueError("camera_count must be >= 1")
    if vram_budget_gb <= 0:
        raise ValueError("vram_budget_gb must be > 0")
    pooled = camera_count >= POOLING_TRIGGER_CAMERAS
    per_process = per_camera_pooled_vram_gb if pooled else per_camera_process_vram_gb
    estimated = None
    if per_process is not None:
        # dedicated: N camera processes; pooled: N weapon/person camera
        # processes + 1 shared violence pool process.
        estimated = per_process * (camera_count + (1 if pooled else 0))
    unmeasured = []
    if per_camera_process_vram_gb is None:
        unmeasured.append("per_camera_process_vram_gb")
    if per_camera_pooled_vram_gb is None:
        unmeasured.append("per_camera_pooled_vram_gb")
    plan = {
        "mode": "pooled-violence" if pooled else "dedicated-per-camera",
        "camera_count": camera_count,
        "inference_processes": camera_count + (1 if pooled else 0),
        "violence_pool_size": 1 if pooled else camera_count,
        "weapon_person_workers": camera_count,
        "pooling_trigger_cameras": POOLING_TRIGGER_CAMERAS,
        "vram_budget_gb": vram_budget_gb,
        "estimated_vram_gb": estimated,
        "unmeasured": unmeasured,
    }
    if estimated is not None:
        plan["headroom_gb"] = vram_budget_gb - estimated
        plan["fits_budget"] = estimated <= vram_budget_gb
    return plan
