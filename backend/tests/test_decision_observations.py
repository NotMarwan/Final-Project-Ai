"""Behavioral regressions for live observations, cooldown and render integration."""
from collections import deque
from queue import Queue
import threading
from unittest.mock import Mock

import numpy as np
import pytest

from backend.decision_config import DecisionConfig, load_decision_config
from backend.fusion import FusionConfig, ThreatFusionEngine
from backend.live_alert_decision import LiveAlertDecisionLayer
from backend.pipeline_render import RenderThread


def policy(**kwargs):
    return load_decision_config().with_updates(**kwargs)


def test_config_round_trip_is_exact_and_runtime_copy_does_not_mutate_default():
    original = load_decision_config()
    assert DecisionConfig.from_mapping(original.to_dict()) == original
    changed = original.with_updates(violence_threshold=0.75)
    assert changed.violence_threshold == 0.75
    assert original.violence_threshold == load_decision_config().violence_threshold


@pytest.mark.parametrize("changes", [
    {"confirm_n": 0}, {"confirm_n": 4, "confirm_m": 3}, {"confirm_m": 1001},
    {"watch_threshold": 0.9}, {"violence_threshold": float("nan")},
    {"weapon_threshold": float("inf")}, {"cooldown_seconds": -1},
    {"confirm_m": 2.5}, {"confirm_n": True}, {"violence_threshold": True},
    {"weapon_display_threshold": 0.99}, {"history_max_age_seconds": 0},
    {"schema_version": 2}, {"severity_high_threshold": 0.2},
])
def test_invalid_config_fails_before_side_effects(changes):
    with pytest.raises(ValueError):
        policy(**changes)


def test_missing_and_unknown_config_keys_are_rejected():
    values = policy().to_dict()
    values.pop("confirm_m")
    with pytest.raises(ValueError):
        DecisionConfig.from_mapping(values)
    with pytest.raises(ValueError):
        DecisionConfig.from_mapping({**policy().to_dict(), "typo": 0.9})


def test_environment_cannot_silently_override_single_policy(monkeypatch):
    monkeypatch.setenv("AI_SENTINEL_WATCH_THRESHOLD", "0.99")
    assert LiveAlertDecisionLayer().watch_threshold == load_decision_config().watch_threshold


def test_every_unique_sample_including_fast_benign_samples_affects_history():
    layer = LiveAlertDecisionLayer(config=policy(confirm_m=4))
    for index, score in enumerate([0.1, 0.8, 0.1, 0.1]):
        result = layer.update(score, sample_time=10 + index * 0.01, sample_id=index)
        assert result["decision_sample_accepted"]
    assert [item["decision_score"] for item in result["rolling_history"]] == [0.1, 0.8, 0.1, 0.1]
    assert [item["calibrated_probability"] for item in result["rolling_history"]] == [None, None, None, None]
    assert result["alert_state"] == "NORMAL"


def test_identical_cached_result_never_gains_votes_despite_elapsed_time():
    layer = LiveAlertDecisionLayer()
    layer.update(0.9, sample_time=10, sample_id=5)
    for now in [10.1, 11, 12, 15]:
        result = layer.update(0.9, sample_time=10, sample_id=5, current_time=now)
        assert not result["confirmed_alert"]
        assert result["history_count"] == 1
        assert result["ignored_reason"] == "stale_sequence"


def test_out_of_order_sequence_and_timestamp_do_not_mutate_history():
    layer = LiveAlertDecisionLayer()
    layer.update(0.9, sample_time=10, sample_id=5)
    result = layer.update(0.9, sample_time=11, sample_id=4)
    assert result["ignored_reason"] == "stale_sequence"
    result = layer.update(0.9, sample_time=9, sample_id=6)
    assert result["ignored_reason"] == "out_of_order_timestamp"
    assert result["history_count"] == 1


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_score_cannot_confirm(score):
    layer = LiveAlertDecisionLayer()
    with pytest.raises(ValueError):
        layer.update(score, sample_time=10, sample_id=1)
    assert layer.status()["history_count"] == 0


def test_expired_vote_and_future_observation_do_not_confirm():
    layer = LiveAlertDecisionLayer(config=policy(history_max_age_seconds=2))
    layer.update(0.9, sample_time=10, sample_id=1)
    result = layer.update(0.9, sample_time=13, sample_id=2)
    assert not result["confirmed_alert"]
    assert result["history_count"] == 1
    future = layer.update(0.9, sample_time=15, sample_id=3, current_time=14)
    assert future["ignored_reason"] == "future_observation"
    expired = layer.update(0.9, sample_time=14, sample_id=3, current_time=20)
    assert expired["ignored_reason"] == "expired_observation"


def test_cooldown_retains_benign_history_and_ticks_cannot_realert():
    layer = LiveAlertDecisionLayer(config=policy(cooldown_seconds=3))
    layer.update(0.9, sample_time=10, sample_id=1)
    confirmed = layer.update(0.9, sample_time=11, sample_id=2)
    assert confirmed["confirmed_alert"]
    duplicate = layer.update(0.9, sample_time=11, sample_id=2, current_time=11.1)
    assert not duplicate["confirmed_alert"]
    low = layer.update(0.1, sample_time=12, sample_id=3)
    assert low["history_count"] == 3
    assert low["alert_state"] == "COOLDOWN"
    expired = layer.status(current_time=14)
    assert expired["alert_state"] == "NORMAL"
    assert not expired["confirmed_alert"]
    assert layer.status(current_time=30)["history_count"] == 0


def test_timestamp_injection_does_not_depend_on_wall_clock(monkeypatch):
    monkeypatch.setattr("backend.live_alert_decision.time.time", lambda: -99999)
    layer = LiveAlertDecisionLayer()
    layer.update(0.9, sample_time=100, sample_id=1)
    result = layer.update(0.9, sample_time=101, sample_id=2)
    assert result["confirmed_alert"]
    assert result["cooldown_remaining_seconds"] == 3


def test_camera_instances_cannot_confirm_each_others_votes():
    left, right = LiveAlertDecisionLayer(), LiveAlertDecisionLayer()
    left.update(0.9, sample_time=10, sample_id=1)
    assert not right.update(0.9, sample_time=11, sample_id=2)["confirmed_alert"]
    assert left.status()["history_count"] == right.status()["history_count"] == 1


def test_policy_changes_clear_votes_but_identical_policy_does_not():
    layer = LiveAlertDecisionLayer()
    layer.update(0.9, sample_time=10, sample_id=1)
    layer.apply_config(layer.config)
    assert layer.status()["history_count"] == 1
    layer.apply_config(policy(confirm_threshold=0.8))
    assert layer.status()["history_count"] == 0


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("motion", [0.0, 0.5, 1.0])
def test_zero_evidence_or_motion_alone_has_no_severity(enabled, motion):
    result = ThreatFusionEngine(FusionConfig(enabled=enabled)).assess(
        violence_confidence=0.0, weapon_score=0.0, motion_score=motion, base_severity="critical")
    assert result["score"] == 0
    assert result["severity"] == "none"


def test_motion_does_not_raise_marginal_evidence_or_positive_score():
    engine = ThreatFusionEngine(FusionConfig())
    assert engine.assess(violence_confidence=0.44, motion_score=1)["score"] == 0
    assert engine.assess(violence_confidence=0.9, motion_score=1)["score"] == engine.assess(violence_confidence=0.9, motion_score=0)["score"]


def test_weapon_display_boundary_uses_policy_and_preserves_top_label():
    engine = ThreatFusionEngine(FusionConfig())
    args = dict(violence_confidence=0, weapon_bbox=[0.2, 0.2, 0.4, 0.4], weapon_labels=["knife", "gun"])
    assert engine.assess_multi_threat(weapon_score=engine.config.policy.weapon_display_threshold - 0.001, **args)["multiThreat"]["threatBoxes"] == []
    boxes = engine.assess_multi_threat(weapon_score=engine.config.policy.weapon_display_threshold, **args)["multiThreat"]["threatBoxes"]
    assert boxes[0]["weaponType"] == "knife"


class RecordingLayer(LiveAlertDecisionLayer):
    def __init__(self):
        super().__init__(config=policy(confirm_m=4))
        self.observed = []

    def update(self, probability, *args, **kwargs):
        self.observed.append(probability)
        return super().update(probability, *args, **kwargs)


def observation(seq, score, **kwargs):
    return {"inference_sequence": seq, "inference_sample_time": 100 + seq,
            "observation_score": score, "threat_confidence": score * 100,
            "violence_conf": score, "is_threat": score >= 0.45,
            "tracks": [], "person_count": 0, "window_valid": True, **kwargs}


def renderer(monkeypatch, layer=None):
    monkeypatch.setattr("backend.pipeline_render.time.monotonic", lambda: 110)
    queue, alerts, metadata = Queue(), [], []
    annotate = Mock(side_effect=lambda **kwargs: kwargs["frame"].copy())
    worker = RenderThread(deque(), None, queue, camera_id="cam-test", decision_layer=layer,
                          annotate_fn=annotate, set_frame_fn=Mock(),
                          set_detection_meta_fn=lambda _camera, snap: metadata.append(snap),
                          on_threat_fn=lambda payload, *_: alerts.append(payload))
    return worker, queue, alerts, metadata, annotate


def test_render_drains_every_observation_and_annotates_every_frame(monkeypatch):
    layer = RecordingLayer()
    worker, queue, alerts, metadata, annotate = renderer(monkeypatch, layer)
    for seq, score in enumerate([0.1, 0.8, 0.1, 0.1], 1):
        queue.put(observation(seq, score))
    frame = np.zeros((32, 32, 3), np.uint8)
    worker._render_frame(frame)
    assert layer.observed == [0.1, 0.8, 0.1, 0.1]
    for _ in range(3):
        worker._render_frame(frame)
    assert annotate.call_count == 4
    assert len(metadata) == 4
    assert not alerts
    assert metadata[-1]["decision_layer"]["history_count"] == 4
    assert metadata[-1]["severity"] == "none"


def test_render_alert_keeps_history_and_cooldown_and_cached_frames_do_not_repeat(monkeypatch):
    layer = RecordingLayer()
    worker, queue, alerts, metadata, _ = renderer(monkeypatch, layer)
    queue.put(observation(1, 0.9))
    queue.put(observation(2, 0.9))
    frame = np.zeros((32, 32, 3), np.uint8)
    worker._render_frame(frame)
    assert len(alerts) == 1
    assert layer.status()["history_count"] == 2
    queue.put(observation(3, 0.1))
    worker._render_frame(frame)
    assert metadata[-1]["decision_layer"]["alert_state"] == "COOLDOWN"
    assert layer.status()["history_count"] == 3
    worker._render_frame(frame)
    assert len(alerts) == 1
    assert alerts[0]["calibratedConfidence"] is None
    assert alerts[0]["alertLatencyMs"] is None


def test_invalid_window_does_not_vote_but_independent_weapon_observation_does(monkeypatch):
    worker, queue, alerts, metadata, _ = renderer(monkeypatch)
    queue.put(observation(1, 0.9, window_valid=False, observation_valid=False))
    frame = np.zeros((32, 32, 3), np.uint8)
    worker._render_frame(frame)
    assert metadata[-1]["decision_layer"]["ignored_reason"] == "invalid_window"
    assert metadata[-1]["decision_layer"]["history_count"] == 0
    queue.put(observation(2, 0.9, window_valid=False, observation_valid=True))
    worker._render_frame(frame)
    assert metadata[-1]["decision_layer"]["history_count"] == 1
    assert not alerts


def test_render_fresh_benign_score_does_not_vote_cached_high_overlay(monkeypatch):
    worker, queue, alerts, metadata, _ = renderer(monkeypatch)
    queue.put(observation(1, 0.1, threat_confidence=99, violence_conf=0.99, is_threat=True))
    queue.put(observation(2, 0.1, threat_confidence=99, violence_conf=0.99, is_threat=True))
    worker._render_frame(np.zeros((32, 32, 3), np.uint8))
    assert not alerts
    assert metadata[-1]["decision_layer"]["alert_state"] == "NORMAL"


def test_new_sequences_with_identical_capture_time_are_distinct_observations():
    layer = LiveAlertDecisionLayer()
    layer.update(0.9, sample_time=100, sample_id=1)
    result = layer.update(0.9, sample_time=100, sample_id=2)
    assert result["confirmed_alert"]
    assert result["history_count"] == 2


def test_rejected_older_timestamp_cannot_rewind_clock_or_extend_cooldown():
    layer = LiveAlertDecisionLayer()
    layer.update(0.9, sample_time=100, sample_id=1)
    layer.update(0.9, sample_time=101, sample_id=2)
    layer.status(current_time=103)
    result = layer.update(0.9, sample_time=99, sample_id=3)
    assert result["cooldown_remaining_seconds"] == 1
    assert layer.status()["cooldown_remaining_seconds"] == 1


def test_run_uses_latest_available_frame_without_sleeping_after_encode():
    stop = threading.Event()
    available = threading.Event()
    frames = deque(["old", "latest"])
    worker = RenderThread(frames, None, stop_event=stop, frame_available=available)
    seen = []

    def render(frame):
        seen.append(frame)
        stop.set()

    worker._render_frame = render
    worker.run()
    assert seen == ["latest"]
    assert not frames


def test_event_clear_race_rechecks_queue_before_waiting():
    stop, frames = threading.Event(), deque()

    class RacingEvent:
        def clear(self):
            frames.append("arrived during clear")

        def wait(self, timeout):
            pytest.fail("Must recheck source queue before waiting")

    worker = RenderThread(frames, None, stop_event=stop, frame_available=RacingEvent())
    seen = []

    def render(frame):
        seen.append(frame)
        stop.set()

    worker._render_frame = render
    worker.run()
    assert seen == ["arrived during clear"]


def test_alert_snapshot_scales_normalized_weapon_box_to_frame_pixels(monkeypatch):
    worker, queue, alerts, metadata, _ = renderer(monkeypatch)
    draw = Mock()
    monkeypatch.setattr("backend.pipeline_render.cv2.rectangle", draw)
    for seq in [1, 2]:
        queue.put(observation(seq, 0.9, weapon_score=0.9, weapon_bbox=[0.25, 0.25, 0.5, 0.75], weapon_labels=["knife"]))
    worker._render_frame(np.zeros((80, 100, 3), np.uint8))
    assert len(alerts) == 1
    assert draw.call_args.args[1:3] == ((25, 20), (50, 60))
