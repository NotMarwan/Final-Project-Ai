"""S-04 / WT-22 scoped tests: HOTA / IDF1 / counting-metric harness.

The metric implementations are validated against sequences with known answers
(perfect tracking must score 1.0; a swapped identity must cost id-consistency)
so the numbers reported on real fixtures mean something.
"""
from __future__ import annotations

import json

import pytest

import eval_tracking as ev
from tracking import FAILURE_FLAG_NAMES


def frame(index: int, gt: list, pred: list, slice_label: str = "normal") -> dict:
    return {"index": index, "slice": slice_label, "gt": gt, "tracks": pred}


def test_perfect_tracking_scores_one_on_every_metric():
    frames = [frame(index, [[1, 0, 0, 10, 20], [2, 40, 0, 50, 20]],
                    [[1, 0, 0, 10, 20], [2, 40, 0, 50, 20]]) for index in range(10)]
    hota = ev.hota(frames)
    assert hota["HOTA"] == pytest.approx(1.0)
    assert hota["DetA"] == pytest.approx(1.0) and hota["AssA"] == pytest.approx(1.0)
    identity = ev.idf1(frames)
    assert identity["IDF1"] == pytest.approx(1.0)
    counting = ev.counting_metrics(frames)
    assert counting["count_mae"] == 0.0
    assert counting["track_switches"] == 0
    assert counting["frames_exact"] == 10


def test_identity_swap_costs_association_and_idf1_but_not_detection():
    """Two people whose predicted ids swap halfway: detections stay perfect."""
    frames = []
    for index in range(10):
        first, second = (1, 2) if index < 5 else (2, 1)
        frames.append(frame(index, [[1, 0, 0, 10, 20], [2, 40, 0, 50, 20]],
                             [[first, 0, 0, 10, 20], [second, 40, 0, 50, 20]]))
    hota = ev.hota(frames)
    assert hota["DetA"] == pytest.approx(1.0)
    assert hota["AssA"] < 0.75
    assert ev.idf1(frames)["IDF1"] < 0.9
    assert ev.counting_metrics(frames)["track_switches"] >= 1


def test_missed_and_duplicate_detections_show_up_in_counting_slices():
    frames = [
        frame(0, [[1, 0, 0, 10, 20], [2, 40, 0, 50, 20]], [[1, 0, 0, 10, 20], [2, 40, 0, 50, 20]]),
        frame(1, [[1, 0, 0, 10, 20], [2, 40, 0, 50, 20]], [[1, 0, 0, 10, 20]], "occlusion"),
        frame(2, [[1, 0, 0, 10, 20]], [[1, 0, 0, 10, 20], [1, 40, 0, 50, 20]], "duplicate"),
    ]
    counting = ev.counting_metrics(frames)
    assert counting["frames_undercounted"] == 1
    assert counting["frames_overcounted"] == 1
    # |0| + |-1| + |+1| over three frames
    assert counting["count_mae"] == pytest.approx(2 / 3)
    assert counting["slices"]["occlusion"]["count_bias"] == pytest.approx(-1.0)
    assert counting["slices"]["duplicate"]["count_bias"] == pytest.approx(1.0)
    assert counting["gt_tracks"] == 2


def test_metrics_handle_empty_frames_without_dividing_by_zero():
    frames = [frame(0, [], []), frame(1, [], [])]
    assert ev.hota(frames)["HOTA"] == 0.0
    assert ev.idf1(frames)["IDF1"] == 0.0
    assert ev.counting_metrics(frames)["frames"] == 2


def test_generated_fixtures_are_deterministic_and_scoreable(tmp_path):
    first = ev.write_synth_fixtures(tmp_path)
    second = ev.write_synth_fixtures(tmp_path)
    assert first == second
    assert len(first) == 6
    for path in first:
        fixture = ev.load_fixture(path)
        assert fixture["frames"]
        report = ev.evaluate_fixture(path, ["bytetrack", "ocsort", "iou_legacy"])
        assert report["frames"] == len(fixture["frames"])
        for name, metrics in report["trackers"].items():
            assert 0.0 <= metrics["HOTA"]["HOTA"] <= 1.0
            assert metrics["IDF1"]["gt_detections"] > 0
            assert set(metrics["failure_flags"]) == set(FAILURE_FLAG_NAMES)
        # The gap-tolerant trackers must not lose identity where the baseline does
        # on the same sequence — that is the whole point of the A/B.
        if fixture["name"] in {"occlusion", "exit_reentry", "missed_person"}:
            assert report["trackers"]["bytetrack"]["IDF1"]["IDF1"] >= report["trackers"]["iou_legacy"]["IDF1"]["IDF1"]


def test_fixture_without_frames_is_rejected(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({"name": "broken"}), encoding="utf-8")
    with pytest.raises(ValueError, match="no frames"):
        ev.load_fixture(path)


def test_run_tracker_returns_the_instance_that_produced_the_output():
    fixture = ev.synth_sequences()["occlusion"]
    frames, tracker = ev.run_tracker(fixture, "bytetrack")
    assert len(frames) == len(fixture["frames"])
    assert tracker.telemetry.snapshot()["dropout"] >= 1
