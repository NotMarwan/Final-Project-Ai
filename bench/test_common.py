import pytest

from bench.common import clip_metrics, distribution


def test_missing_measurements_are_not_zero():
    assert distribution([])["p95"] is None
    assert clip_metrics([])["precision"] is None


def test_percentiles_include_slow_tail():
    result = distribution([1, 2, 3, 4, 100])
    assert result["p50"] == 3
    assert result["p95"] == 80.8


def test_invalid_measurements_are_rejected():
    with pytest.raises(ValueError):
        distribution([1, float("nan")])


def test_unknown_labels_and_incomplete_runs_cannot_pass_accuracy():
    result = clip_metrics([
        {"label": "negative", "alert_count": 0, "completed": True},
        {"label": "positive", "label_verified": True, "completed": False, "alert_count": 1},
        {"label": "positive", "label_verified": True, "completed": True, "alert_count": 0},
        {"label": "negative", "label_verified": True, "completed": True, "alert_count": 1},
    ])
    assert result["unevaluated"] == 2
    assert result["fn"] == 1 and result["fp"] == 1
    assert result["recall"] == 0
