"""S-04 / WT-22 scoped test: the alert dispatch path is not slowed by capture.

This is the concrete proof the campaign requires for the async capture queue:
`RenderThread._emit_alert` must behave identically with incident capture enabled
(one O(1) enqueue) and with it disabled, and no scoring may happen inline.
"""
from __future__ import annotations

import time
from collections import deque

import numpy as np
import pytest

from capture_queue import IncidentCapture
from frame_pipeline import OverlayCache
from live_alert_decision import LiveAlertDecisionLayer
from pipeline_render import RenderThread

DECISION = {"alert_state": "CONFIRMED", "confirm_rule": "2_of_3"}


def snap() -> dict:
    return {
        "is_threat": True, "threat_confidence": 90.0, "weapon_score": 0.0, "weapon_labels": [],
        "violence_conf": 0.9, "motion_score": 0.5, "observation_score": 0.9,
        "weapon_bbox": None, "violence_bbox": None, "video_width": 1280, "video_height": 720,
        "person_count": 2, "active_track_count": 2, "visible_person_count": 3,
        "unique_person_estimate_window": {"estimate": 2, "band_label": "±1", "windowSeconds": 60},
        "track_failure_flags": {"drift": 1}, "person_tracker": "bytetrack", "fps": 20.0,
        "tracks": [{"track_ref": "CAM-1::1"}, {"track_ref": "CAM-1::2"}],
    }


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def build_renderer(capture=None) -> RenderThread:
    return RenderThread(
        frame_queue=deque(), result_cache=OverlayCache(), camera_id="CAM-1",
        decision_layer=LiveAlertDecisionLayer(), incident_capture=capture,
    )


def test_alert_payload_carries_counting_and_capture_state_without_identity_claims():
    clock = FakeClock()
    delivered = []
    capture = IncidentCapture(pre_seconds=5.0, post_seconds=1.0, clock=clock, camera_id="CAM-1")
    capture.feed(clock.now, np.zeros((32, 32, 3), np.uint8), frame_sequence=1)
    renderer = build_renderer(capture)
    renderer.on_threat_fn = lambda payload, jpeg, clip_path: delivered.append(payload)

    renderer._emit_alert(snap(), DECISION, np.zeros((32, 32, 3), np.uint8))
    capture.stop()

    payload = delivered[0]
    assert payload["visiblePersonCount"] == 3
    assert payload["activeTrackCount"] == 2
    assert payload["personCount"] == 2  # documented alias
    assert payload["personTracker"] == "bytetrack"
    assert payload["trackFailureFlags"] == {"drift": 1}
    assert payload["trackNamespace"] == "CAM-1"
    assert payload["uniquePersonEstimateWindow"]["bandLabel"] == "±1"
    assert payload["capture"]["state"] == "pending"
    assert payload["capture"]["alertId"] == payload["id"]


def test_alert_path_latency_is_unaffected_by_enabling_capture():
    base = build_renderer(None)
    base.on_threat_fn = lambda payload, jpeg, clip_path: None
    frame = np.zeros((64, 64, 3), np.uint8)

    def measure(renderer: RenderThread, runs: int = 5) -> float:
        durations = []
        for _ in range(runs):
            started = time.perf_counter()
            renderer._emit_alert(snap(), DECISION, frame)
            durations.append((time.perf_counter() - started) * 1000)
        durations.sort()
        return durations[len(durations) // 2]

    baseline_ms = measure(base)

    clock = FakeClock()
    capture = IncidentCapture(pre_seconds=5.0, post_seconds=3.0, clock=clock, camera_id="CAM-1")
    for index in range(20):
        capture.feed(clock.now + index * 0.25, np.zeros((32, 32, 3), np.uint8), frame_sequence=index)
    renderer = build_renderer(capture)
    renderer.on_threat_fn = lambda payload, jpeg, clip_path: None
    with_capture_ms = measure(renderer)
    capture.stop()

    # The enqueue must be a rounding error next to JPEG/annotation work: allow a
    # generous 5 ms absolute delta so the test is not timing-flaky, but a
    # synchronous capture pass (scoring ~20 frames) would blow far past it.
    assert with_capture_ms - baseline_ms < 5.0, f"capture added {with_capture_ms - baseline_ms:.2f} ms to the alert path"


def test_capture_failure_degrades_capture_health_and_never_the_alert():
    class BrokenCapture:
        def trigger(self, **_kwargs):
            raise RuntimeError("capture subsystem down")

    delivered = []
    renderer = build_renderer(BrokenCapture())
    renderer.on_threat_fn = lambda payload, jpeg, clip_path: delivered.append(payload)
    renderer._emit_alert(snap(), DECISION, np.zeros((32, 32, 3), np.uint8))

    assert len(delivered) == 1, "the alert must still be delivered"
    assert renderer._health["incident_capture"] == "degraded"
    assert "capture" not in delivered[0]


def test_detection_payload_includes_the_canonical_counting_fields():
    from api import _build_detection_payload

    payload = _build_detection_payload(snap(), "CAM-1")
    assert payload["visiblePersonCount"] == 3
    assert payload["activeTrackCount"] == 2
    assert payload["trackFailureFlags"] == {"drift": 1}
    assert payload["trackNamespace"] == "CAM-1"
    assert payload["personTracker"] == "bytetrack"


def test_person_broadcast_is_change_detected_and_throttled():
    from api import _broadcast_person_counts, state

    queue = state.subscribe()
    try:
        _broadcast_person_counts("CAM-THROTTLE", snap())
        first = queue.get_nowait()
        assert '"type": "person_detection"' in first
        assert '"visiblePersonCount": 3' in first
        assert '"bandLabel"' in first
        # Identical snapshot again -> nothing new is emitted.
        _broadcast_person_counts("CAM-THROTTLE", snap())
        assert queue.empty()
        # A changed count is emitted once the rate limit has elapsed.
        time.sleep(0.3)
        changed = {**snap(), "active_track_count": 5}
        _broadcast_person_counts("CAM-THROTTLE", changed)
        assert '"activeTrackCount": 5' in queue.get_nowait()
    finally:
        state.unsubscribe(queue)
