"""G-06 calibration policy: artifact validation, consumption and startup refusal.

All fixtures here are SYNTHETIC SELF-TEST mechanics. They verify the machinery,
they are never evidence, and they are never used as test truth (EXP-21).
"""
from __future__ import annotations

import json
import hashlib
import logging
import math

import pytest

from backend.calibration_utils import (
    CALIBRATION_OVERRIDE_ENV,
    CALIBRATION_OVERRIDE_PHRASE,
    CalibrationArtifactError,
    calibration_state,
    enforce_startup_calibration,
    load_calibration_profile,
    normalize_calibration_profile,
    validate_calibration_artifact,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def artifact(**overrides):
    payload = {
        "schema_version": 1,
        "status": "candidate-not-runtime-validated",
        "method": "binary-temperature-scaling",
        "temperature": 1.37,
        "model_sha256": HASH_A,
        "input_sha256": HASH_B,
        "calibration": {"count": 12, "nll": 0.5, "brier": 0.2, "ece": 0.05, "ece_bins": 15},
        "held_out_before": {"count": 10, "nll": 0.6, "brier": 0.25, "ece": 0.09, "ece_bins": 15},
        "held_out_after": {"count": 10, "nll": 0.5, "brier": 0.2, "ece": 0.04, "ece_bins": 15},
        "limitations": ["auxiliary-domain candidate; not in-domain CCTV calibration"],
    }
    payload.update(overrides)
    return payload


def test_valid_artifact_is_accepted_and_normalized_for_consumption():
    validated = validate_calibration_artifact(artifact())
    assert validated["temperature"] == 1.37
    profile = normalize_calibration_profile(artifact())
    # Artifact consumption: inference.py reads logitTemperature (F-40 contract).
    assert profile["logitTemperature"] == 1.37
    assert profile["calibration_status"] == "calibrated-candidate"


@pytest.mark.parametrize("overrides", [
    {"schema_version": 2},
    {"temperature": float("nan")},
    {"temperature": 0.0},
    {"temperature": -1.0},
    {"model_sha256": "not-a-hash"},
    {"method": "vibes"},
    {"limitations": []},
    {"status": "calibrated"},
])
def test_invalid_artifacts_are_refused(overrides):
    with pytest.raises(CalibrationArtifactError):
        validate_calibration_artifact(artifact(**overrides))


def test_startup_refuses_without_artifact_or_override(tmp_path, monkeypatch):
    monkeypatch.delenv(CALIBRATION_OVERRIDE_ENV, raising=False)
    monkeypatch.delenv("AI_SENTINEL_ENV", raising=False)
    with pytest.raises(CalibrationArtifactError) as excinfo:
        enforce_startup_calibration(base_dir=tmp_path, env=dict())
    message = str(excinfo.value)
    assert CALIBRATION_OVERRIDE_ENV in message
    assert "calibration artifact" in message.lower()


def test_development_override_is_loud_and_works(tmp_path, monkeypatch):
    env = {CALIBRATION_OVERRIDE_ENV: CALIBRATION_OVERRIDE_PHRASE}
    with caplog_context() as records:
        state = enforce_startup_calibration(base_dir=tmp_path, env=env, production=False)
    assert state["status"] == "unverified"
    assert state["dev_override"] is True
    joined = "\n".join(record.getMessage() for record in records)
    assert "UNVERIFIED" in joined
    assert any(record.levelno >= logging.CRITICAL for record in records)


def test_override_is_impossible_in_production(tmp_path):
    env = {CALIBRATION_OVERRIDE_ENV: CALIBRATION_OVERRIDE_PHRASE,
           "AI_SENTINEL_ENV": "production"}
    with pytest.raises(CalibrationArtifactError):
        enforce_startup_calibration(base_dir=tmp_path, env=env)
    with pytest.raises(CalibrationArtifactError):
        enforce_startup_calibration(base_dir=tmp_path, env=env, production=True)


def test_silent_or_wrong_override_is_refused(tmp_path):
    for env in ({}, {CALIBRATION_OVERRIDE_ENV: ""}, {CALIBRATION_OVERRIDE_ENV: "true"},
                {CALIBRATION_OVERRIDE_ENV: CALIBRATION_OVERRIDE_PHRASE.lower()}):
        with pytest.raises(CalibrationArtifactError):
            enforce_startup_calibration(base_dir=tmp_path, env=env, production=False)


def test_valid_artifact_unlocks_startup_without_override(tmp_path):
    model = tmp_path / "best_model.pt"
    model.write_bytes(b"synthetic-model-not-deployable")
    payload = artifact(model_sha256=hashlib.sha256(model.read_bytes()).hexdigest())
    (tmp_path / "model_calibration.json").write_text(json.dumps(payload), encoding="utf-8")
    state = enforce_startup_calibration(base_dir=tmp_path, env=dict())
    assert state["status"] == "calibrated-candidate"
    assert state["temperature"] == 1.37
    assert state["dev_override"] is False


def test_corrupt_artifact_file_is_loud_not_silent(tmp_path, caplog):
    (tmp_path / "model_calibration.json").write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.ERROR):
        profile = load_calibration_profile(base_dir=tmp_path)
    assert profile == {}
    assert any(record.levelno >= logging.ERROR for record in caplog.records)


def test_missing_artifact_keeps_status_unverified(tmp_path):
    state = calibration_state(base_dir=tmp_path)
    assert state["status"] == "unverified"
    assert state["temperature"] is None


class caplog_context:
    def __enter__(self):
        import logging as _logging
        self._handler = _logging.Handler()
        self.records = []
        self._handler.emit = self.records.append
        _logging.getLogger().addHandler(self._handler)
        self._level = _logging.getLogger().level
        _logging.getLogger().setLevel(_logging.DEBUG)
        return self.records

    def __exit__(self, *exc):
        import logging as _logging
        _logging.getLogger().removeHandler(self._handler)
        _logging.getLogger().setLevel(self._level)
        return False


def test_wrong_checkpoint_cannot_unlock_startup_or_apply_temperature(tmp_path):
    (tmp_path / "best_model.pt").write_bytes(b"different-synthetic-model")
    (tmp_path / "model_calibration.json").write_text(json.dumps(artifact()), encoding="utf-8")
    assert load_calibration_profile(base_dir=tmp_path) == {}
    assert calibration_state(base_dir=tmp_path)["calibrated"] is False
    with pytest.raises(CalibrationArtifactError):
        enforce_startup_calibration(base_dir=tmp_path, env={})


def test_calibration_cache_follows_model_replacement_and_explicit_path(tmp_path):
    model = tmp_path / "alternative.pt"
    model.write_bytes(b"first-synthetic-model")
    payload = artifact(model_sha256=hashlib.sha256(model.read_bytes()).hexdigest())
    (tmp_path / "model_calibration.json").write_text(json.dumps(payload), encoding="utf-8")
    assert calibration_state(base_dir=tmp_path, model_path=model)["calibrated"] is True
    assert calibration_state(base_dir=tmp_path)["calibrated"] is False
    model.write_bytes(b"a-replacement-model-with-different-size")
    assert calibration_state(base_dir=tmp_path, model_path=model)["calibrated"] is False


def test_changed_temperature_override_invalidates_artifact_and_cache(tmp_path, monkeypatch):
    model = tmp_path / "best_model.pt"
    model.write_bytes(b"synthetic-model")
    payload = artifact(model_sha256=hashlib.sha256(model.read_bytes()).hexdigest())
    (tmp_path / "model_calibration.json").write_text(json.dumps(payload), encoding="utf-8")
    assert calibration_state(base_dir=tmp_path)["calibrated"] is True
    monkeypatch.setenv("VIOLENCE_LOGIT_TEMPERATURE", "2.5")
    assert calibration_state(base_dir=tmp_path)["calibrated"] is False
    assert load_calibration_profile(base_dir=tmp_path) == {}


def test_legacy_tuning_file_cannot_self_assert_calibrated_status(tmp_path):
    (tmp_path / "model_calibration.json").write_text(json.dumps({
        "calibration_status": "calibrated", "logitTemperature": 1.4,
    }), encoding="utf-8")
    assert calibration_state(base_dir=tmp_path)["calibrated"] is False
    with pytest.raises(CalibrationArtifactError):
        enforce_startup_calibration(base_dir=tmp_path, env={})


def test_explicit_checkpoint_uses_its_own_calibrated_class(tmp_path, monkeypatch):
    import torch
    from backend.inference import ViolenceInferencePipeline

    model = tmp_path / "alternative.pt"
    model.write_bytes(b"synthetic-checkpoint-class-zero")
    artifact_path = tmp_path / "calibration.json"
    artifact_path.write_text(json.dumps(artifact(
        model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(), classIndex=0,
    )), encoding="utf-8")
    monkeypatch.setenv("MODEL_CALIBRATION_PATH", str(artifact_path))
    monkeypatch.delenv("VIOLENCE_CLASS_INDEX", raising=False)
    pipeline = ViolenceInferencePipeline.__new__(ViolenceInferencePipeline)
    pipeline._configure_score_profile(str(model))
    logits = torch.tensor([[2.0, 0.0]])
    raw = torch.softmax(logits, dim=-1)[0, pipeline._class_index].item()
    assert pipeline._class_index == 0
    assert raw > .8
    assert pipeline._logit_margin_of(logits, pipeline._class_index) == 2.0
    assert pipeline._calibrate_confidence(logits, raw) == pytest.approx(1 / (1 + math.exp(-2 / 1.37)))


@pytest.mark.parametrize("class_index", [-1, 2, True, "0"])
def test_invalid_artifact_class_is_unverified(tmp_path, class_index):
    model = tmp_path / "best_model.pt"
    model.write_bytes(b"synthetic-class-check")
    payload = artifact(model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(), classIndex=class_index)
    (tmp_path / "model_calibration.json").write_text(json.dumps(payload), encoding="utf-8")
    assert calibration_state(base_dir=tmp_path)["calibrated"] is False
