"""S-05 hardening: R5 confidence-weighted N-of-M + anchor gate, uncertainty
semantics, modality independence, confirm-latency measurement, alert severity
floor (R-3 server side).

Fixtures are synthetic mechanics only (never evidence / never test truth).
"""
from __future__ import annotations

from collections import deque
from queue import Queue
from unittest.mock import Mock

import numpy as np
import pytest

from backend.decision_config import load_decision_config
from backend.fusion import FusionConfig, ThreatFusionEngine
from backend.live_alert_decision import LiveAlertDecisionLayer
from backend.pipeline_render import RenderThread
from backend.inference_process import _select_fresh_observation_score


def policy(**kwargs):
    return load_decision_config().with_updates(**kwargs)


def votes(layer, scores, start=10.0, step=0.1, first_id=1):
    results = []
    for index, score in enumerate(scores):
        results.append(layer.update(score, sample_time=start + index * step, sample_id=first_id + index))
    return results


def confirmed_steps(results):
    return [index for index, result in enumerate(results) if result["confirmed_alert"]]


# --- R5: defaults reproduce the classic 2-of-3 rule EXACTLY (equivalence) ---

SEQUENCES = [
    [0.9, 0.9],
    [0.9, 0.1, 0.9],
    [0.9, 0.1, 0.1],
    [0.7, 0.7, 0.7],
    [0.66, 0.66],
    [0.9, 0.1, 0.1, 0.9, 0.9],
    [0.5, 0.5, 0.5],
]


def first_classic_step(scores, confirm_threshold, confirm_n, confirm_m):
    for index in range(len(scores)):
        window = scores[max(0, index - confirm_m + 1):index + 1]
        if sum(p >= confirm_threshold for p in window) >= confirm_n:
            return index
    return None


@pytest.mark.parametrize("scores", SEQUENCES)
def test_default_weighted_rule_confirms_exactly_when_the_classic_rule_first_does(scores):
    cfg = policy()
    layer = LiveAlertDecisionLayer(config=cfg)
    steps = confirmed_steps(votes(layer, scores))
    expected = first_classic_step(scores, cfg.confirm_threshold, cfg.confirm_n, cfg.confirm_m)
    assert steps == ([] if expected is None else [expected])


# --- R5: confidence-weighted sum and anchor gate actually bite ---

def test_weight_sum_rejects_barely_qualifying_votes_until_a_strong_vote_arrives():
    layer = LiveAlertDecisionLayer(config=policy(confirm_weight_sum=2.5, confirm_weight_gain=1.0))
    weak = votes(layer, [0.66, 0.66])
    assert weak[-1]["alert_state"] == "WATCH"
    assert not confirmed_steps(weak)
    strong = votes(layer, [0.9], start=10.2, first_id=3)
    assert confirmed_steps(strong)


def test_anchor_gate_requires_a_peak_score():
    gated = LiveAlertDecisionLayer(config=policy(cascade_gate_threshold=0.8))
    assert not confirmed_steps(votes(gated, [0.7, 0.7, 0.7, 0.7]))
    ungated = LiveAlertDecisionLayer(config=policy())
    assert confirmed_steps(votes(ungated, [0.7, 0.7, 0.7, 0.7]))


def test_anchor_gate_confirms_when_peak_crosses_gate():
    layer = LiveAlertDecisionLayer(config=policy(cascade_gate_threshold=0.8))
    assert confirmed_steps(votes(layer, [0.7, 0.85]))


def test_rule_fields_are_reported():
    layer = LiveAlertDecisionLayer(config=policy(confirm_weight_sum=2.5, confirm_weight_gain=0.5,
                                                 cascade_gate_threshold=0.8))
    result = layer.update(0.9, sample_time=1, sample_id=1)
    assert result["confirm_weight_sum"] == 2.5
    assert result["confirm_weight_gain"] == 0.5
    assert result["cascade_gate_threshold"] == 0.8
    assert "weight" in result["confirm_rule"]


# --- uncertainty semantics: calibrated probability vs raw score vs severity ---

def test_response_labels_every_quantity_and_keeps_raw_separate_from_calibrated():
    layer = LiveAlertDecisionLayer()
    result = layer.update(0.9, sample_time=1, sample_id=1)
    semantics = result["score_semantics"]
    assert result["model_score"] == 0.9
    assert result["calibrated_probability"] is None  # no artifact -> never a probability
    assert "decision score" in semantics["model_score"].lower()
    assert result["raw_model_score"] is None
    assert result["score_source"] == "unknown"
    assert semantics["severity"].startswith("rule-based")
    entry = result["rolling_history"][0]
    assert entry["model_score"] == 0.9
    assert entry["calibrated_probability"] is None
    assert entry["calibration_status"] == "unverified"
    assert "per-observation" in semantics["rolling_history_calibrated_probability"].lower()


def test_calibrated_probability_present_when_artifact_active():
    layer = LiveAlertDecisionLayer(calibration_state={"status": "calibrated-candidate"})
    result = layer.update(0.9, sample_time=1, sample_id=1)
    assert result["calibrated_probability"] == 0.9
    assert result["score_semantics"]["calibrated_probability"].startswith("temperature-scaled")


def test_active_violence_artifact_does_not_calibrate_raw_weapon_vote():
    layer = LiveAlertDecisionLayer(calibration_state={"status": "calibrated-candidate"})
    decision = layer.update(
        0.92,
        sample_time=100.0,
        sample_id=1,
        calibrated_value=None,
        raw_model_score=0.92,
        score_source="weapon",
        score_calibration_status="unverified",
    )
    assert decision["model_score"] == pytest.approx(0.92)
    assert decision["raw_model_score"] == pytest.approx(0.92)
    assert decision["calibrated_probability"] is None
    assert decision["calibration_status"] == "unverified"
    assert decision["rolling_history"][0]["calibrated_probability"] is None

    alerts = []
    worker = RenderThread(deque(), None, None, camera_id="cam-test", decision_layer=layer,
                          on_threat_fn=lambda payload, *_: alerts.append(payload))
    snapshot = {
        "observation_score": 0.92,
        "observation_score_source": "weapon",
        "observation_raw_model_score": 0.92,
        "observation_calibrated_probability": None,
        "observation_calibration_status": "unverified",
        "weapon_score": 0.01,
        "weapon_raw_model_score": 0.92,
        "violence_conf": 0.4,
        "violence_raw_model_score": 0.17,
        "person_count": 0,
        "tracks": [],
    }
    worker._emit_alert(snapshot, decision, np.zeros((32, 32, 3), dtype=np.uint8))
    assert len(alerts) == 1
    payload = alerts[0]
    assert payload["scoreSource"] == "weapon"
    assert payload["threatType"] == "weapon"
    assert payload["type"] == "Weapon"
    assert payload["rawModelScore"] == pytest.approx(0.92)
    assert payload["rawModelConfidence"] == pytest.approx(0.17)
    assert payload["calibratedProbability"] is None
    assert payload["calibrationStatus"] == "unverified"


def test_legacy_observation_does_not_fabricate_raw_score_fields():
    layer = LiveAlertDecisionLayer()
    decision = layer.update(0.91, sample_time=100.0, sample_id=1)
    alerts = []
    worker = RenderThread(deque(), None, None, camera_id="cam-test", decision_layer=layer,
                          on_threat_fn=lambda payload, *_: alerts.append(payload))
    worker._emit_alert({
        "observation_score": 0.91,
        "violence_conf": 0.91,
        "weapon_score": 0.0,
        "person_count": 0,
        "tracks": [],
    }, decision, np.zeros((32, 32, 3), dtype=np.uint8))

    assert len(alerts) == 1
    assert alerts[0]["rawModelScore"] is None
    assert alerts[0]["rawModelConfidence"] is None
    assert alerts[0]["calibratedProbability"] is None


def test_candidate_violence_probability_is_preserved_as_its_own_value():
    layer = LiveAlertDecisionLayer(calibration_state={"status": "calibrated-candidate"})
    result = layer.update(
        0.81,
        sample_time=100.0,
        sample_id=1,
        calibrated_value=0.73,
        raw_model_score=0.91,
        score_source="violence",
        score_calibration_status="calibrated-candidate",
    )
    assert result["model_score"] == pytest.approx(0.81)
    assert result["raw_model_score"] == pytest.approx(0.91)
    assert result["calibrated_probability"] == pytest.approx(0.73)
    assert result["rolling_history"][0]["calibrated_probability"] == pytest.approx(0.73)


def test_unverified_producer_cannot_publish_a_calibrated_value():
    layer = LiveAlertDecisionLayer(calibration_state={"status": "calibrated-candidate"})
    result = layer.update(
        0.81,
        sample_time=100.0,
        sample_id=1,
        calibrated_value=0.73,
        raw_model_score=0.91,
        score_source="weapon",
        score_calibration_status="unverified",
    )
    assert result["calibrated_probability"] is None
    assert result["calibration_status"] == "unverified"


def test_new_violence_observation_does_not_reuse_cached_weapon_vote():
    selected = _select_fresh_observation_score(
        fresh_violence=True,
        violence={"source": "violence", "score": 0.42},
        fresh_weapon=False,
        weapon={"source": "weapon", "score": 0.99},
    )
    assert selected == {"source": "violence", "score": 0.42}


def test_new_weapon_observation_does_not_reuse_cached_violence_vote():
    selected = _select_fresh_observation_score(
        fresh_violence=False,
        violence={"source": "violence", "score": 0.99},
        fresh_weapon=True,
        weapon={"source": "weapon", "score": 0.42},
    )
    assert selected == {"source": "weapon", "score": 0.42}


def test_simultaneously_fresh_modalities_select_the_larger_source_score():
    selected = _select_fresh_observation_score(
        fresh_violence=True,
        violence={"source": "violence", "score": 0.71},
        fresh_weapon=True,
        weapon={"source": "weapon", "score": 0.85},
    )
    assert selected == {"source": "weapon", "score": 0.85}


# --- measurement: decision confirm latency on ONE monotonic clock (WT-13) ---

def test_confirm_latency_measured_window_open_to_confirmed_and_never_zero_fabricated():
    layer = LiveAlertDecisionLayer()
    assert layer.status()["decision_confirm_latency_ms"] is None
    layer.update(0.9, sample_time=100.0, sample_id=1)
    assert layer.status()["decision_confirm_latency_ms"] is None
    result = layer.update(0.9, sample_time=101.5, sample_id=2)
    assert result["confirmed_alert"]
    assert result["decision_confirm_latency_ms"] == pytest.approx(1500.0)
    assert "NOT glass-to-alert" in result["decision_confirm_latency_clock"]


def test_confirm_latency_fields_are_always_published_for_the_telemetry_consumer():
    layer = LiveAlertDecisionLayer()
    responses = [layer.status(), layer.update(0.9, sample_time=1.0, sample_id=1)]
    for response in responses:
        assert "decision_confirm_latency_ms" in response
        assert response["decision_confirm_latency_clock"].startswith("decision-monotonic")
    assert all(r["decision_confirm_latency_ms"] is None for r in responses)


# --- modality independence in fusion (no silent weapon->violence coupling) ---

def test_fusion_never_lets_weapon_evidence_inflate_the_violence_score():
    engine = ThreatFusionEngine(FusionConfig())
    alone = engine.assess(violence_confidence=0.5, weapon_score=0.0)
    with_weapon = engine.assess(violence_confidence=0.5, weapon_score=0.99)
    assert alone["violenceScore"] == with_weapon["violenceScore"]


def test_fusion_never_lets_violence_evidence_inflate_the_weapon_score():
    engine = ThreatFusionEngine(FusionConfig())
    alone = engine.assess(violence_confidence=0.0, weapon_score=0.5)
    with_violence = engine.assess(violence_confidence=0.99, weapon_score=0.5)
    assert alone["weaponScore"] == with_violence["weaponScore"]


def test_person_count_and_motion_cannot_change_fused_score_or_severity():
    engine = ThreatFusionEngine(FusionConfig())
    base = engine.assess(violence_confidence=0.8, weapon_score=0.2, motion_score=0.0)
    for motion in (0.5, 1.0):
        moved = engine.assess(violence_confidence=0.8, weapon_score=0.2, motion_score=motion)
        assert moved["score"] == base["score"]
        assert moved["severity"] == base["severity"]


def test_multi_threat_boxes_do_not_change_the_fused_score_and_person_count_is_not_an_input():
    import inspect
    assert "person_count" not in inspect.signature(ThreatFusionEngine.assess).parameters
    assert "person_count" not in inspect.signature(ThreatFusionEngine.assess_multi_threat).parameters
    engine = ThreatFusionEngine(FusionConfig())
    plain = engine.assess(violence_confidence=0.8, weapon_score=0.3)
    boxed = engine.assess_multi_threat(violence_confidence=0.8, weapon_score=0.3,
                                       weapon_bbox=[0.1, 0.1, 0.2, 0.2], weapon_labels=["pistol"])
    assert boxed["score"] == plain["score"]
    assert boxed["severity"] == plain["severity"]


def test_fusion_consumes_coarse_weapon_group_and_never_subtypes_for_severity():
    engine = ThreatFusionEngine(FusionConfig())
    firearm = engine.assess_multi_threat(violence_confidence=0.0, weapon_score=0.9,
                                         weapon_bbox=[0.1, 0.1, 0.2, 0.2], weapon_labels=["pistol"],
                                         weapon_group="firearm")
    edged = engine.assess_multi_threat(violence_confidence=0.0, weapon_score=0.9,
                                       weapon_bbox=[0.1, 0.1, 0.2, 0.2], weapon_labels=["sword"],
                                       weapon_group="edged")
    assert firearm["multiThreat"]["threatBoxes"][0]["weaponType"] == "gun"
    assert edged["multiThreat"]["threatBoxes"][0]["weaponType"] == "knife"
    assert firearm["severity"] == edged["severity"]


def test_fusion_score_semantics_labels_fused_score():
    result = ThreatFusionEngine(FusionConfig()).assess(violence_confidence=0.9, weapon_score=0.0)
    assert "rule-based" in result["scoreSemantics"]["score"].lower()


# --- alert payload quantity labeling + severity floor (R-3) ---

def renderer(monkeypatch):
    monkeypatch.setattr("backend.pipeline_render.time.monotonic", lambda: 110)
    queue, alerts, metadata = Queue(), [], []
    worker = RenderThread(deque(), None, queue, camera_id="cam-test",
                          annotate_fn=lambda **kwargs: kwargs["frame"].copy(),
                          set_frame_fn=Mock(),
                          set_detection_meta_fn=lambda _camera, snap: metadata.append(snap),
                          on_threat_fn=lambda payload, *_: alerts.append(payload))
    return worker, queue, alerts, metadata


def observation(seq, score, **extra):
    return {"inference_sequence": seq, "inference_sample_time": 100 + seq,
            "observation_score": score, "threat_confidence": score * 100,
            "violence_conf": score, "is_threat": True,
            "tracks": [], "person_count": 0, "window_valid": True, **extra}


def test_alert_payload_labels_quantities_and_carries_confirm_latency(monkeypatch):
    worker, queue, alerts, _ = renderer(monkeypatch)
    queue.put(observation(1, 0.9))
    queue.put(observation(2, 0.9))
    worker._render_frame(np.zeros((32, 32, 3), np.uint8))
    assert len(alerts) == 1
    payload = alerts[0]
    semantics = payload["scoreSemantics"]
    assert payload["rawModelScore"] is None
    assert payload["rawModelConfidence"] is None
    assert payload["calibratedProbability"] is None
    assert payload["calibrationStatus"] == "unverified"
    assert payload["severitySource"] == "rule-based-band-of-fused-score-min-medium"
    assert semantics["calibratedConfidence"].startswith("temperature-scaled")
    # Fixture clocks: oldest vote sample_time 101, render decision clock 110 -> 9.0 s window-open->confirmed.
    assert payload["decisionConfirmLatencyMs"] == pytest.approx(9000.0)


def test_alert_payload_mirrors_onset_window_identity_additively(monkeypatch):
    worker, queue, alerts, _ = renderer(monkeypatch)
    extra = {"violence_onset_candidate_timestamp": 100.5, "violence_onset_candidate_window_id": 7,
             "violence_window_id": 9, "violence_window_start_timestamp": 99.0,
             "violence_window_end_timestamp": 100.0}
    queue.put(observation(1, 0.9, **extra))
    queue.put(observation(2, 0.9, **extra))
    worker._render_frame(np.zeros((32, 32, 3), np.uint8))
    assert len(alerts) == 1
    assert alerts[0]["onsetCandidateAt"] == 100.5
    assert alerts[0]["onsetCandidateWindowId"] == 7
    assert alerts[0]["violenceWindowId"] == 9
    assert alerts[0]["violenceWindowStartTimestamp"] == 99.0
    assert alerts[0]["violenceWindowEndTimestamp"] == 100.0


def test_confirmed_alert_severity_is_never_none_even_below_medium_threshold(monkeypatch):
    layer = LiveAlertDecisionLayer(config=policy(watch_threshold=0.1, confirm_threshold=0.1,
                                                 severity_medium_threshold=0.99,
                                                 severity_high_threshold=0.995,
                                                 severity_critical_threshold=1.0))
    worker, queue, alerts, _ = renderer(monkeypatch)
    worker._decision_layer = layer
    queue.put(observation(1, 0.2))
    queue.put(observation(2, 0.2))
    worker._render_frame(np.zeros((32, 32, 3), np.uint8))
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "medium"
