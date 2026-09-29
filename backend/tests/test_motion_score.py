import numpy as np

from backend.inference_process import (
    _motion_thumbnail,
    _score_motion_thumbnails,
    estimate_motion_score,
)


def test_cached_motion_thumbnails_preserve_motion_score():
    previous = np.zeros((360, 480, 3), dtype=np.uint8)
    current = previous.copy()
    current[40:180, 120:260] = (40, 120, 220)

    expected = estimate_motion_score(previous, current)
    cached = _score_motion_thumbnails(_motion_thumbnail(previous), _motion_thumbnail(current))

    assert cached == expected


def test_missing_motion_thumbnail_scores_zero():
    frame = np.zeros((64, 64, 3), dtype=np.uint8)

    assert _score_motion_thumbnails(None, _motion_thumbnail(frame)) == 0.0
