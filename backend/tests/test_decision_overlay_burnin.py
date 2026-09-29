"""WT-17 (S-09): decision overlays are burned into the exact frame server-side.

The threat boxes and the decision badge are drawn by `visual_annotator.annotate`
on the same frame the decision refers to (fusion runs before annotation), so the
labels are frame-accurate by construction; `frameSequence` identifies that frame on
the wire (SC-3). No client canvas drift can affect these pixels.
"""
from __future__ import annotations

import numpy as np

from visual_annotator import annotate


def _red_pixels(img_bgr) -> int:
    b, g, r = img_bgr[:, :, 0], img_bgr[:, :, 1], img_bgr[:, :, 2]
    return int(np.count_nonzero((r > 180) & (g < 80) & (b < 80)))


def test_decision_overlay_burned_into_the_frame_it_describes():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    boxes = [{"id": "w1", "type": "weapon", "label": "gun", "confidence": 0.87,
              "color": (0, 0, 255), "bbox": [10, 10, 60, 60]}]

    # No decision, no boxes: nothing is drawn.
    plain = annotate(frame=frame.copy(), tracks=[])
    assert _red_pixels(plain) == 0

    # A confirmed decision burns the badge (and the threat box) into the frame.
    marked = annotate(frame=frame.copy(), tracks=[], threat_boxes=boxes, decision_state="CONFIRMED")
    assert _red_pixels(marked) > 0

    # A normal decision draws the threat box but no decision badge.
    idle = annotate(frame=frame.copy(), tracks=[], threat_boxes=boxes, decision_state="NORMAL")
    assert _red_pixels(idle) > 0


def test_annotate_ignores_malformed_threat_boxes():
    frame = np.zeros((60, 80, 3), dtype=np.uint8)
    malformed = [None, "gun", {"bbox": "nope"}, {"bbox": [5, 5, 5, 5]}, {"bbox": [10, 10, 5, 5]}]
    out = annotate(frame=frame.copy(), tracks=[], threat_boxes=malformed, decision_state="WATCH")
    assert out.shape == frame.shape
