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
    # Extended fields for parallel pipeline
    violence_conf: float = 0.0
    violence_label: str = ""
    motion_score: float = 0.0
    video_width: int = 0
    video_height: int = 0
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
            "violence_conf": "violence_conf",
            "motion_score": "motion_score",
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
