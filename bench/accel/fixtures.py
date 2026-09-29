"""Deterministic fixture frames for WT-16 measurements.

Primary source: the operator's demo clip (read-only untracked asset, hash
recorded in every report). If the clip is absent, a seeded synthetic fallback
keeps the harness runnable; reports must then say source mode `synthetic`.

Source mode is always recorded explicitly: `file-media` frames are media-clock
content and must never be described as live capture.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

# Fixed indices -> identical inputs for every run and both execution providers.
FRAME_INDICES = (0, 15, 30, 45, 60, 75, 90, 105, 120, 135)
SYNTHETIC_SEED = 20260929
DEFAULT_VIDEO = Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/cam3.mp4")
_FALLBACK_SIZE = (720, 1280)  # h, w — matches cam3.mp4


def _synthetic_frames() -> tuple[list[np.ndarray], dict]:
    rng = np.random.default_rng(SYNTHETIC_SEED)
    h, w = _FALLBACK_SIZE
    frames = [rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8) for _ in FRAME_INDICES]
    digest = hashlib.sha256()
    for frame in frames:
        digest.update(frame.tobytes())
    return frames, {"source": f"synthetic:seed={SYNTHETIC_SEED}", "sourceMode": "synthetic",
                    "sourceSha256": digest.hexdigest(), "frameIndices": list(FRAME_INDICES)}


def load_frames(video: Path | str | None = None) -> tuple[list[np.ndarray], dict]:
    """Return (frames, manifest). Frames are raw BGR uint8 HxWx3."""
    path = Path(video) if video is not None else DEFAULT_VIDEO
    if not path.exists():
        return _synthetic_frames()
    import cv2
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        return _synthetic_frames()
    frames = []
    try:
        for index in FRAME_INDICES:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                return _synthetic_frames()
            frames.append(np.ascontiguousarray(frame))
    finally:
        capture.release()
    return frames, {"source": str(path), "sourceMode": "file-media", "sourceSha256": digest,
                    "frameIndices": list(FRAME_INDICES),
                    "resolution": [int(frames[0].shape[1]), int(frames[0].shape[0])]}
