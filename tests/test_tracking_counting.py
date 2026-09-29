"""S-04 / WT-22 scoped tests: trackers, counting semantics, tracking path.

These lock the behaviour that the campaign requires of the tracking slice:
ByteTrack/OC-SORT on boxes only (no ReID), surfaced track-failure taxonomy,
and the canonical counting definitions.
"""
from __future__ import annotations

import numpy as np
import pytest

from counting import CountingSemantics
from tracking import (FAILURE_FLAG_NAMES, TRACKER_FACTORIES, box_iou,
                      create_tracker, iou_matrix, xyxy_to_xyah, xyah_to_xyxy)


def det(*rows: tuple[float, float, float, float, float]) -> np.ndarray:
    return np.asarray(rows, dtype=np.float64).reshape(-1, 5)


@pytest.mark.parametrize("name", sorted(TRACKER_FACTORIES))
def test_identity_survives_a_detection_gap_for_gap_tolerant_trackers(name):
    tracker = create_tracker(name)
    tracker.update(det((0, 0, 10, 20, 0.9)))
    tracker.update(det((1, 0, 11, 20, 0.9)))
    tracker.update(det())
    tracks = tracker.update(det((2, 0, 12, 20, 0.9)))
    ids = [track["track_id"] for track in tracks]
    if name == "iou_legacy":
        # Baseline behaviour: a missed frame drops the track and the id is lost.
        assert ids == [2]
    else:
        assert ids == [1]


@pytest.mark.parametrize("name", ["bytetrack", "ocsort"])
def test_track_failure_flags_are_reported_never_absorbed(name):
    tracker = create_tracker(name)
    tracker.update(det((0, 0, 10, 20, 0.9)))
    tracker.update(det())
    tracker.update(det((0, 0, 10, 20, 0.9)))
    flags = tracker.telemetry.snapshot()
    assert set(flags) == set(FAILURE_FLAG_NAMES)
    assert flags["dropout"] == 1
    event = tracker.telemetry.events[-1]
    assert event["flag"] == "dropout" and event["gap_frames"] == 1

    deltas = tracker.telemetry.drain_deltas()
    assert deltas["dropout"] == 1
    assert tracker.telemetry.drain_deltas()["dropout"] == 0  # deltas are consumed once


def test_id_switch_and_reentry_are_classified_by_gap_length():
    tracker = create_tracker("iou_legacy")
    tracker.update(det((0, 0, 10, 20, 0.9)))
    tracker.update(det((1, 0, 11, 20, 0.9)))
    tracker.update(det())  # legacy drops the track immediately
    # Same location returns after one missed frame -> identity handoff.
    tracker.update(det((2, 0, 12, 20, 0.9)))
    assert tracker.telemetry.snapshot()["id_switch"] == 1

    long_gap = create_tracker("iou_legacy")
    long_gap.update(det((0, 0, 10, 20, 0.9)))
    for _ in range(5):
        long_gap.update(det())
    long_gap.update(det((0, 0, 10, 20, 0.9)))
    assert long_gap.telemetry.snapshot()["re_entry"] == 1
    assert long_gap.telemetry.snapshot()["id_switch"] == 0


def test_drift_flag_fires_on_a_low_iou_association():
    tracker = create_tracker("bytetrack")
    tracker.update(det((0, 0, 40, 80, 0.9)))
    # IoU 0.25: still matched (association floor is 0.2) but a large correction.
    tracker.update(det((24, 0, 64, 80, 0.9)))
    assert tracker.telemetry.snapshot()["drift"] >= 1


def test_merge_split_flag_fires_when_two_tracks_collapse_onto_one_box():
    tracker = create_tracker("bytetrack")
    tracker.update(det((0, 0, 20, 40, 0.9), (60, 0, 80, 40, 0.9)))
    tracker.update(det((40, 0, 60, 40, 0.9), (40, 0, 60, 40, 0.9)))
    assert tracker.telemetry.snapshot()["merge_split"] >= 1


def test_low_confidence_detection_above_the_detector_gate_is_still_tracked():
    # The person path derives tracker thresholds from the detector confidence;
    # otherwise people detected between the two thresholds would be counted as
    # visible but never tracked.
    tracker = create_tracker("bytetrack", track_thresh=0.45, new_track_thresh=0.45, low_thresh=0.225)
    assert tracker.update(det((0, 0, 10, 20, 0.5)))[0]["track_id"] == 1


def test_trackers_never_receive_or_use_appearance_features():
    """ReID is excluded by policy: the update surface is boxes+scores only."""
    import inspect

    for factory in TRACKER_FACTORIES.values():
        signature = inspect.signature(factory.update)
        assert list(signature.parameters) == ["self", "detections"]


def test_geometry_helpers_match_known_values():
    assert box_iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)
    assert box_iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    matrix = iou_matrix(np.asarray([[0, 0, 10, 10]]), np.asarray([[0, 0, 10, 10], [0, 0, 5, 5]]))
    assert matrix[0, 0] == pytest.approx(1.0)
    assert matrix[0, 1] == pytest.approx(0.25)
    assert iou_matrix(np.zeros((0, 4)), np.zeros((2, 4))).shape == (0, 2)
    box = [1.0, 2.0, 11.0, 22.0]
    assert xyah_to_xyxy(xyxy_to_xyah(box)) == pytest.approx(box)


def test_unknown_tracker_parameter_is_rejected_not_ignored():
    with pytest.raises(ValueError, match="unknown tracker parameter"):
        create_tracker("bytetrack", nonsense=1)
    with pytest.raises(ValueError, match="unknown tracker"):
        create_tracker("deepsort")


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_counting_definitions_are_distinct_and_windowed():
    clock = _Clock()
    counting = CountingSemantics(window_seconds=10.0, clock=clock)
    snapshot = counting.observe(clock.now, visible_person_count=3, track_refs=["cam::1", "cam::2"])
    assert snapshot["visible_person_count"] == 3
    assert snapshot["active_track_count"] == 2
    window = snapshot["unique_person_estimate_window"]
    assert window["window_seconds"] == 10.0
    assert window["unique_track_ids"] == 2
    assert window["band_label"] == "±0"
    assert window["band_is_calibrated"] is False
    assert window["estimate_lower"] == 2 and window["estimate_upper"] == 2

    # A new identity inside the window widens the set…
    clock.now += 1.0
    counting.observe(clock.now, visible_person_count=1, track_refs=["cam::3"],
                     failure_deltas={"id_switch": 2, "dropout": 1})
    window = counting.last_snapshot()["unique_person_estimate_window"]
    assert window["unique_track_ids"] == 3
    assert window["band_label"] == "±3"
    assert window["estimate_lower"] == 0 and window["estimate_upper"] == 6

    # …and the window really expires (band events included).
    clock.now += 30.0
    snapshot = counting.observe(clock.now, visible_person_count=1, track_refs=["cam::9"])
    window = snapshot["unique_person_estimate_window"]
    assert window["unique_track_ids"] == 1
    assert window["band_label"] == "±0"


def test_counting_rejects_a_non_positive_window():
    with pytest.raises(ValueError, match="window_seconds"):
        CountingSemantics(window_seconds=0.0)


def test_person_detector_counting_stats_contract():
    """`latest_counting_stats()` is the duck-typed provider contract with WT-15."""
    from person_detector import PersonDetector

    detector = PersonDetector(camera_id="CAM-07")
    assert detector.enabled is True  # no model load happens at construction
    assert detector.latest_counting_stats() == {"person_tracker": "bytetrack"}

    # Default min_track_frames=3: the identity is not yet confirmed, so the
    # window counter stays empty rather than reporting an unconfirmed id.
    detector._update_tracks(det((0, 0, 10, 20, 0.9)), timestamp=1000.0)
    assert detector.latest_counting_stats()["visible_person_count"] == 1
    assert detector.latest_counting_stats()["unique_person_estimate_window"]["unique_track_ids"] == 0

    confirmed = PersonDetector(camera_id="CAM-07", min_track_frames=1)
    confirmed._update_tracks(det((0, 0, 10, 20, 0.9)), timestamp=1000.0)
    stats = confirmed.latest_counting_stats()
    assert set(stats) == {"person_tracker", "visible_person_count",
                          "unique_person_estimate_window", "track_failure_flags"}
    assert stats["visible_person_count"] == 1
    assert stats["unique_person_estimate_window"]["unique_track_ids"] == 1
    assert stats["track_failure_flags"] == {name: 0 for name in FAILURE_FLAG_NAMES}
    assert "active_track_count" not in stats  # owned by the inference worker


def test_person_detector_tracks_carry_camera_scoped_refs():
    from person_detector import PersonDetector

    detector = PersonDetector(camera_id="CAM-07", min_track_frames=1)
    detector._update_tracks(det((0, 0, 10, 20, 0.9)), timestamp=1000.0)
    tracks = detector._get_active_tracks()
    assert tracks[0]["track_ref"] == "CAM-07::1"
    assert tracks[0]["camera_id"] == "CAM-07"


def test_min_track_frames_still_gates_the_overlay_output():
    from person_detector import PersonDetector

    detector = PersonDetector(camera_id="CAM-07", min_track_frames=3)
    detector._update_tracks(det((0, 0, 10, 20, 0.9)), timestamp=1000.0)
    assert detector._get_active_tracks() == []
    detector._update_tracks(det((0, 0, 10, 20, 0.9)), timestamp=1000.1)
    detector._update_tracks(det((0, 0, 10, 20, 0.9)), timestamp=1000.2)
    assert len(detector._get_active_tracks()) == 1
