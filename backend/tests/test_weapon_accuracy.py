"""Weapon score calibration + honest evaluation-boundary contracts (WT-18).

Replaces the previous synthetic-noise "accuracy" suite, which asserted
>=90% accuracy / >=85% precision on random images with invented labels —
per the campaign honesty rule synthetic frames MUST NEVER serve as test
truth (WT-07 §2.7), so those assertions were not evidence of anything and
are removed rather than re-pinned.

What this file covers instead:
  * F-40 calibration artifact binding to the scored ONNX sha256, with the
    "candidate never reports as calibrated" rule.
  * The F-09 boundary fields `rawModelScore` / `calibratedProbability` /
    `calibrationStatus`.
  * A registered-model smoke gated on an explicit opt-in (env
    WEAPON_ONNX_SMOKE=1) because a real forward pass is a measured run and
    measured runs must hold the campaign RESOURCE-LOCK, not fire inside an
    arbitrary test session.

Real per-class metrics are produced by
`backend/tools/weapon_fp_log_run.py` over the WT-12 fixture harness media
(G-02 negatives / G-03 positives); that harness's fixture manifest is
`docs/campaign/eval/12-fixture-manifest.json` and its media root is outside
this git worktree (see the WT-18 handoff for the blocked/unblocked status).
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root for bench.*

from weapon import (WeaponConfig, WeaponSignalEngine, _ONNXBackend,  # noqa: E402
                    load_decision_policy)
from weapon_calibration import (STATUS_ABSENT, STATUS_CANDIDATE,  # noqa: E402
                                STATUS_MISMATCH_REJECTED, CalibrationError,
                                WeaponScoreCalibration, calibrated_probability,
                                load_calibration_artifact)


def _artifact(tmp_path: Path, **overrides) -> Path:
    payload = {
        "schema_version": 1,
        "status": "candidate-not-runtime-validated",
        "method": "binary-temperature-scaling",
        "temperature": 1.75,
        "model_sha256": "a" * 64,
        "calibration": {"count": 10, "nll": 0.4, "brier": 0.2, "ece": 0.1, "ece_bins": 15},
        "held_out_before": {"count": 8, "nll": 0.5, "brier": 0.25, "ece": 0.2, "ece_bins": 15},
        "held_out_after": {"count": 8, "nll": 0.45, "brier": 0.22, "ece": 0.15, "ece_bins": 15},
        "input_sha256": "c" * 64,
    }
    payload.update(overrides)
    path = tmp_path / "weapon_temperature.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_calibration_artifact_must_bind_to_the_scored_model(tmp_path):
    path = _artifact(tmp_path)
    artifact = load_calibration_artifact(path, expected_model_sha256="a" * 64)
    assert artifact.temperature == pytest.approx(1.75)
    assert artifact.reported_status == STATUS_CANDIDATE
    with pytest.raises(CalibrationError, match="different model"):
        load_calibration_artifact(path, expected_model_sha256="b" * 64)


def test_mismatched_artifact_is_rejected_loudly_not_silently_applied(tmp_path):
    path = _artifact(tmp_path)
    calibration = WeaponScoreCalibration.from_path(path, expected_model_sha256="b" * 64)
    assert calibration.status == STATUS_MISMATCH_REJECTED
    assert calibration.rejection_reason
    assert calibration.apply(0.9) is None
    assert WeaponScoreCalibration.from_path(None).status == STATUS_ABSENT


def test_candidate_artifact_never_reports_as_calibrated(tmp_path):
    path = _artifact(tmp_path)
    calibration = WeaponScoreCalibration.from_path(path, expected_model_sha256="a" * 64)
    assert calibration.status == STATUS_CANDIDATE
    assert calibration.status != "calibrated"


def test_invalid_artifacts_are_rejected(tmp_path):
    with pytest.raises(CalibrationError, match="temperature"):
        load_calibration_artifact(_artifact(tmp_path, temperature=0))
    with pytest.raises(CalibrationError, match="model_sha256"):
        load_calibration_artifact(_artifact(tmp_path, model_sha256="short"))
    with pytest.raises(CalibrationError, match="status"):
        load_calibration_artifact(_artifact(tmp_path, status="validated-ish"))
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(CalibrationError, match="valid JSON"):
        load_calibration_artifact(broken)


def test_calibrated_probability_matches_bench_calibrate_math():
    from bench.calibrate import scale as bench_scale
    for score in (0.01, 0.2, 0.5, 0.77, 0.99):
        for temperature in (0.5, 1.0, 1.75, 4.0):
            assert calibrated_probability(score, temperature) == pytest.approx(
                bench_scale(score, temperature), abs=1e-12)
    with pytest.raises(CalibrationError, match="probability"):
        calibrated_probability(1.5, 1.0)
    with pytest.raises(CalibrationError, match="temperature"):
        calibrated_probability(0.5, -1.0)


def test_engine_exposes_raw_and_calibrated_scores_at_the_boundary(tmp_path):
    path = _artifact(tmp_path)
    calibration = WeaponScoreCalibration.from_path(path, expected_model_sha256="a" * 64)
    engine = WeaponSignalEngine(WeaponConfig(interval=1, min_interval_ms=0),
                                torch.device("cpu"), calibration=calibration)
    engine._backend = SimpleNamespace(predict=lambda frame: [(.8, 'pistol', [.1, .1, .2, .2])])
    engine._infer_async(np.zeros((8, 8, 3)))
    signal = engine.latest_signal()
    assert signal["rawModelScore"] == pytest.approx(.8)
    assert signal["calibratedProbability"] == pytest.approx(
        calibrated_probability(.8, 1.75), abs=1e-12)
    assert signal["calibrationStatus"] == STATUS_CANDIDATE
    assert signal["calibrationStatus"] != "calibrated"
    # Without an artifact the calibrated value stays null and status absent.
    plain = WeaponSignalEngine(WeaponConfig(interval=1, min_interval_ms=0),
                               torch.device("cpu"))
    plain._backend = SimpleNamespace(predict=lambda frame: [(.8, 'pistol', [.1, .1, .2, .2])])
    plain._infer_async(np.zeros((8, 8, 3)))
    assert plain.latest_signal()["calibratedProbability"] is None
    assert plain.latest_signal()["calibrationStatus"] == STATUS_ABSENT


def _registered_onnx_path() -> Path:
    override = os.environ.get("WEAPON_ONNX_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "models" / "weapon_yolo.onnx"


@pytest.mark.skipif(os.environ.get("WEAPON_ONNX_SMOKE") != "1",
                    reason="real forward pass is a measured run; set "
                           "WEAPON_ONNX_SMOKE=1 and hold the campaign RESOURCE-LOCK")
def test_registered_onnx_backend_records_model_hash_and_decodes():
    """Opt-in smoke on the registered weapon export (untracked asset)."""
    model_path = _registered_onnx_path()
    if not model_path.is_file():
        pytest.skip(f"weapon ONNX not present in this checkout: {model_path}")
    with model_path.open("rb") as stream:
        expected = hashlib.file_digest(stream, "sha256").hexdigest()
    backend = _ONNXBackend(str(model_path), load_decision_policy().weapon_min_confidence,
                           ("pistol", "rifle", "shotgun", "knife", "sword", "revolver"))
    assert backend.model_sha256 == expected
    assert backend.execution_provider
    assert backend.input_size == (640, 640)
    hits = backend.predict(np.zeros((480, 640, 3), dtype=np.uint8))
    assert isinstance(hits, list)
    for score, label, bbox in hits:
        assert 0.0 <= score <= 1.0
        assert label in backend.categories
        assert all(0.0 <= value <= 1.0 for value in bbox)
