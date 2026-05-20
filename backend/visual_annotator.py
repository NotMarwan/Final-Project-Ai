from __future__ import annotations

import os
from typing import Optional

import cv2
import numpy as np

_BOX_LW_NORMAL = 2
_BOX_LW_THREAT = 3
_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.45
_LINE_AA = cv2.LINE_AA
_FAST_DEFAULT = os.getenv("AI_SENTINEL_FAST_ANNOTATE", "false").lower() in {"1", "true", "yes", "on"}


def _track_get(track, key, default=None):
    """Get attribute from track — works with both dicts and objects."""
    if isinstance(track, dict):
        return track.get(key, default)
    return getattr(track, key, default)


def annotate(
    frame: np.ndarray,
    tracks: list,
    person_count: int = 0,
    is_threat: bool = False,
    threat_confidence: float = 0.0,
    camera_id: str = "",
    fps: float = 0.0,
    threat_person_box: Optional[list[float]] = None,
    fast: Optional[bool] = None,
) -> np.ndarray:
    img = frame
    use_fast = _FAST_DEFAULT if fast is None else fast

    if not use_fast:
        for track in tracks:
            trail = _track_get(track, "trail", [])
            if len(trail) < 2:
                continue
            color = _track_get(track, "color", (0, 255, 255))
            pts = np.array(trail, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(img, [pts], False, color, 2, _LINE_AA)

    for track in tracks:
        x1, y1, x2, y2 = map(int, _track_get(track, "bbox", [0, 0, 0, 0]))
        color = _track_get(track, "color", (0, 255, 255))
        conf = _track_get(track, "confidence", 0.0)
        label = _track_get(track, "label", "?")
        lw = _BOX_LW_THREAT if is_threat else _BOX_LW_NORMAL
        cv2.rectangle(img, (x1, y1), (x2, y2), color, lw, _LINE_AA)
        badge_text = f"{label} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(badge_text, _FONT, _FONT_SCALE, 1)
        cv2.rectangle(img, (x1, max(0, y1 - th - 6)), (x1 + tw + 10, y1), color, -1, _LINE_AA)
        cv2.putText(img, badge_text, (x1 + 5, max(0, y1 - 4) + th), _FONT, _FONT_SCALE, (0, 0, 0), 1, _LINE_AA)

    return img
