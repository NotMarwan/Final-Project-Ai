from __future__ import annotations

import math
import os
import time
from typing import Optional

import cv2
import numpy as np

_BOX_LW_NORMAL = 2
_BOX_LW_THREAT = 3
_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.45
_LINE_AA = cv2.LINE_AA
_FAST_DEFAULT = os.getenv("AI_SENTINEL_FAST_ANNOTATE", "true").lower() in {"1", "true", "yes", "on"}


def _dark_outline(img: np.ndarray, text: str, org, font, scale, thickness, color):
    """Draw text with a dark outline for contrast on any background."""
    cv2.putText(img, text, org, font, scale, (0, 0, 0,), thickness + 2, _LINE_AA)
    cv2.putText(img, text, org, font, scale, color, thickness, _LINE_AA)


def _draw_rounded_rect(img, pt1, pt2, color, lw, radius=4):
    x1, y1 = pt1
    x2, y2 = pt2
    cv2.rectangle(img, (x1, y1), (x2, y2), color, lw, _LINE_AA)


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
    h, w = img.shape[:2]
    use_fast = _FAST_DEFAULT if fast is None else fast

    if not use_fast:
        for track in tracks:
            trail = getattr(track, "trail", [])
            if len(trail) < 2:
                continue
            color = getattr(track, "color", (0, 255, 255))
            pts = np.array(trail, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(img, [pts], False, color, 2, _LINE_AA)

    for track in tracks:
        x1, y1, x2, y2 = map(int, getattr(track, "bbox", [0, 0, 0, 0]))
        color = getattr(track, "color", (0, 255, 255))
        conf = getattr(track, "confidence", 0.0)
        label = getattr(track, "label", "?")
        lw = _BOX_LW_THREAT if is_threat else _BOX_LW_NORMAL
        cv2.rectangle(img, (x1, y1), (x2, y2), color, lw, _LINE_AA)
        badge_text = f"{label} {conf:.0%}"
        (tw, th), _ = cv2.getTextSize(badge_text, _FONT, _FONT_SCALE, 1)
        cv2.rectangle(img, (x1, max(0, y1 - th - 6)), (x1 + tw + 10, y1), color, -1, _LINE_AA)
        cv2.putText(img, badge_text, (x1 + 5, max(0, y1 - 4) + th), _FONT, _FONT_SCALE, (0, 0, 0), 1, _LINE_AA)

    count_text = f"PERSONS: {person_count}"
    count_color = (0, 60, 255) if is_threat else (0, 255, 255)
    _dark_outline(img, count_text, (12, 28), _FONT, 0.55, 1, count_color)

    if camera_id:
        _dark_outline(img, camera_id, (12, h - 14), _FONT, 0.4, 1, (180, 180, 180))

    fps_text = f"{fps:.0f} FPS"
    (fw, _), _ = cv2.getTextSize(fps_text, _FONT, 0.4, 1)
    _dark_outline(img, fps_text, (w - fw - 12, h - 14), _FONT, 0.4, 1, (180, 180, 180))

    if is_threat:
        threat_text = f"VIOLENCE {threat_confidence:.0f}%" if use_fast else f"VIOLENCE DETECTED  {threat_confidence:.0f}%"
        (tw, th), _ = cv2.getTextSize(threat_text, _FONT, 0.65, 2)
        banner_x = (w - tw) // 2 - 20
        banner_y = 12
        banner_w = tw + 40
        banner_h = th + 16
        cv2.rectangle(img, (banner_x, banner_y), (banner_x + banner_w, banner_y + banner_h), (0, 0, 180), -1)
        cv2.rectangle(img, (banner_x, banner_y), (banner_x + banner_w, banner_y + banner_h), (0, 50, 255), 1, _LINE_AA)
        cv2.putText(img, threat_text, (banner_x + 20, banner_y + th + 6), _FONT, 0.65, (0, 100, 255), 2, _LINE_AA)

        if not use_fast:
            pulse_alpha = 0.3 + 0.2 * math.sin(time.time() * 4)
            overlay = img.copy()
            cv2.rectangle(overlay, (0, 0), (w - 1, h - 1), (0, 0, 200), 4, _LINE_AA)
            cv2.addWeighted(overlay, pulse_alpha, img, 1 - pulse_alpha, 0, img)

    return img
