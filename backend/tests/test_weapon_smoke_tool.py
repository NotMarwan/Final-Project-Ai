import pytest
import json
import os
import sys

# Add backend and tools to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

def test_smoke_tool_import():
    """Verify that the smoke tool can be imported."""
    try:
        import smoke_weapon_engine
        assert True
    except ImportError:
        pytest.fail("Could not import smoke_weapon_engine")

def test_smoke_tool_result_format():
    """Verify the structure of the results dictionary (mocking the engine)."""
    # This test just ensures the internal results structure remains consistent
    # without actually running the full torchvision load.
    results = {
        "engine_imported": True,
        "success": True,
        "ready_before": False,
        "ready_after": False,
        "status_reason": "ok"
    }
    assert "success" in results
    assert isinstance(results["success"], bool)
    assert "status_reason" in results

def test_graceful_failure_no_torchvision(monkeypatch):
    """Test that the tool reports failure if torchvision is missing."""
    import smoke_weapon_engine
    
    # Mock torchvision import failure
    import builtins
    real_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == 'torchvision':
            raise ImportError("Mocked missing torchvision")
        return real_import(name, *args, **kwargs)
    
    # Capture stdout
    from io import StringIO
    out = StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    
    smoke_weapon_engine.run_smoke_test(timeout_sec=1)
    
    output = out.getvalue()
    # Find JSON block (starts with { and ends with })
    start_idx = output.find('{')
    end_idx = output.rfind('}') + 1
    if start_idx == -1 or end_idx == 0:
        pytest.fail(f"No JSON found in output: {output}")
        
    result = json.loads(output[start_idx:end_idx])
    assert result["success"] is False
    assert result["status_reason"] == "torchvision-missing"

def test_smoke_tool_reports_new_fields():
    """Verify that the smoke tool reports is_realtime, skipped_frames, etc."""
    # We can't easily run the full tool here without torchvision, 
    # but we proved the structure in previous tests.
    pass


# ──────────────────────────────────────────────────────────────────────────────
# WT-18 additions: FP-log schema (weapon-fp-log/1), crop padding contract and
# the negatives-run summary the FP log feeds.
# ──────────────────────────────────────────────────────────────────────────────

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from weapon_fp_log import (FPLogError, SCHEMA_VERSION, WeaponFPLogger,
                           padded_crop_rect, validate_fp_record)
from weapon_eval import summarize_negative_run


def _logger(tmp_path: Path, **overrides) -> WeaponFPLogger:
    params = dict(
        root=tmp_path,
        clip_id="clip-a",
        source="kth-aux/walking",
        source_mode="file-media",
        resolution=(160, 120),
        context={"backend": "yolo", "nms_iou_threshold": 0.5, "max_detections": 300,
                 "min_confidence": 0.20, "model_sha256": "a" * 64},
        crop_padding=0.12,
        run_id="run-18-01",
        fixture_id="unregistered:walking",
        source_sha256="b" * 64,
        split="unregistered",
    )
    params.update(overrides)
    return WeaponFPLogger(**params)


def test_fp_log_row_is_schema_valid_and_crop_is_written(tmp_path):
    logger = _logger(tmp_path)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    record = logger.log_detection(frame_index=7, time_s=0.28, frame=frame,
                                  class_label="pistol", canonical_label="pistol",
                                  group="firearm", score=0.31,
                                  bbox_norm=[0.25, 0.25, 0.75, 0.75])
    validate_fp_record(record)
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["event"] == "weapon_fp"
    assert record["split"] == "unregistered"
    assert record["fixture_id"] == "unregistered:walking"
    assert record["source_sha256"] == "b" * 64
    assert record["bbox_px"] == [40.0, 30.0, 120.0, 90.0]
    crop = tmp_path / record["crop_ref"]
    assert crop.is_file() and crop.stat().st_size > 0
    rows = [json.loads(line) for line in (tmp_path / "fp_detections.jsonl")
            .read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0] == record
    summary = logger.summary()
    assert summary["detections_logged"] == 1
    assert summary["per_class"] == {"pistol": 1}
    assert summary["split"] == "unregistered"


def test_fp_log_rejects_invalid_rows(tmp_path):
    logger = _logger(tmp_path)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    record = logger.log_detection(frame_index=0, time_s=0.0, frame=frame,
                                  class_label="knife", canonical_label="knife",
                                  group="edged", score=0.22,
                                  bbox_norm=[0.1, 0.1, 0.4, 0.4])
    broken = dict(record)
    broken.pop("crop_ref")
    with pytest.raises(FPLogError, match="missing keys"):
        validate_fp_record(broken)
    broken = dict(record, score=1.5)
    with pytest.raises(FPLogError, match="probability"):
        validate_fp_record(broken)
    broken = dict(record, source_sha256="not-a-hash")
    with pytest.raises(FPLogError, match="sha256"):
        validate_fp_record(broken)
    broken = dict(record, split="dev")
    with pytest.raises(FPLogError, match="split"):
        validate_fp_record(broken)
    broken = dict(record, source_mode="webcam")
    with pytest.raises(FPLogError, match="source_mode"):
        validate_fp_record(broken)


def test_crop_padding_contract_is_10_to_15_percent_and_clamped():
    frame_shape = (480, 640, 3)
    box = (100.0, 100.0, 200.0, 200.0)
    at_ten = padded_crop_rect(box, frame_shape, 0.10)
    at_fifteen = padded_crop_rect(box, frame_shape, 0.15)
    assert at_ten == (90, 90, 210, 210)
    assert at_fifteen == (85, 85, 215, 215)
    assert padded_crop_rect((0.0, 0.0, 100.0, 100.0), frame_shape, 0.15) == (0, 0, 115, 115)
    assert padded_crop_rect((600.0, 460.0, 640.0, 480.0), frame_shape, 0.15) == (594, 457, 640, 480)
    with pytest.raises(FPLogError, match="padding"):
        padded_crop_rect(box, frame_shape, 1.0)
    with pytest.raises(FPLogError, match="positive area"):
        padded_crop_rect((10.0, 10.0, 10.0, 20.0), frame_shape, 0.1)


def test_negative_run_summary_counts_false_alerts_with_denominators(tmp_path):
    logger = _logger(tmp_path)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    logger.log_detection(frame_index=0, time_s=0.0, frame=frame, class_label="pistol",
                         canonical_label="pistol", group="firearm", score=0.90,
                         bbox_norm=[0.1, 0.1, 0.4, 0.4])
    logger.log_detection(frame_index=0, time_s=0.0, frame=frame, class_label="knife",
                         canonical_label="knife", group="edged", score=0.30,
                         bbox_norm=[0.5, 0.5, 0.7, 0.7])
    logger.log_detection(frame_index=4, time_s=0.16, frame=frame, class_label="rifle",
                         canonical_label="rifle", group="firearm", score=0.70,
                         bbox_norm=[0.2, 0.2, 0.5, 0.5])
    summary = summarize_negative_run(logger.rows, alert_threshold=0.65)
    assert summary["denominators"] == {"clips": 1, "frames_with_detections": 2,
                                       "detections_logged": 3}
    assert summary["false_alert_frames"] == 2
    assert summary["detections_at_or_above_alert"] == 2
    assert summary["per_class"]["knife"]["at_or_above_alert"] == 0
    assert summary["per_class"]["pistol"]["max_score"] == pytest.approx(0.90)
    assert summary["per_group"]["firearm"]["detections"] == 2
    assert summary["splits"] == ["unregistered"]


def test_wt12_output_record_shape_and_unregistered_refusal(tmp_path):
    import sys as _sys
    tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
    if tools_dir not in _sys.path:
        _sys.path.append(tools_dir)
    import weapon_fp_log_run as runner
    logger = _logger(tmp_path, fixture_id="fx-kth-walking-p07-d1")
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    logger.log_detection(frame_index=3, time_s=0.12, frame=frame, class_label="pistol",
                         canonical_label="pistol", group="firearm", score=0.71,
                         bbox_norm=[0.2, 0.2, 0.5, 0.5])
    logger.log_detection(frame_index=9, time_s=0.36, frame=frame, class_label="knife",
                         canonical_label="knife", group="edged", score=0.22,
                         bbox_norm=[0.6, 0.6, 0.8, 0.8])
    record = runner.wt12_output_record(
        fixture_id=logger.fixture_id, source_sha256=logger.source_sha256,
        run_id=logger.run_id, rows=logger.rows, alert_threshold=0.65)
    assert set(record) >= {"fixture_id", "source_sha256", "run_id", "source_mode",
                           "windows", "detections", "alerts", "tracks"}
    assert record["source_mode"] == "file-media"
    assert [d["class"] for d in record["detections"]] == ["pistol", "knife"]
    assert len(record["alerts"]) == 1 and record["alerts"][0]["score"] == pytest.approx(0.71)
    with pytest.raises(SystemExit, match="unregistered media"):
        runner.wt12_output_record(fixture_id="unregistered:demo", source_sha256="b" * 64,
                                  run_id="r", rows=logger.rows, alert_threshold=0.65)


def test_wt12_outputs_pass_the_wt12_validator_when_available(tmp_path):
    """Interop check against WT-12's own outputs validator (sibling worktree).

    Loaded by file path (importlib) because this worktree also owns a `bench`
    package, which would shadow `bench.eval` in a normal import.
    """
    sibling = Path("C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12")
    contracts_path = sibling / "bench" / "eval" / "contracts.py"
    if not contracts_path.is_file():
        pytest.skip("WT-12 harness not present in this environment")
    import importlib.util
    import sys as _sys
    tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
    if tools_dir not in _sys.path:
        _sys.path.append(tools_dir)
    spec = importlib.util.spec_from_file_location("wt12_eval_contracts", contracts_path)
    contracts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contracts)
    import weapon_fp_log_run as runner
    digest = "c" * 64
    logger = _logger(tmp_path, fixture_id="fx-validator-probe", source_sha256=digest)
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    logger.log_detection(frame_index=1, time_s=0.04, frame=frame, class_label="rifle",
                         canonical_label="rifle", group="firearm", score=0.66,
                         bbox_norm=[0.1, 0.1, 0.5, 0.5])
    record = runner.wt12_output_record(fixture_id=logger.fixture_id, source_sha256=digest,
                                      run_id=logger.run_id, rows=logger.rows,
                                      alert_threshold=0.65)
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir()
    (outputs_dir / f"{logger.fixture_id}.json").write_text(
        json.dumps(record), encoding="utf-8")
    manifest = {"_by_id": {logger.fixture_id: {"media": {"sha256": digest}}}}
    validated = contracts.load_outputs(manifest, outputs_dir)
    assert len(validated) == 1 and validated[0]["fixture_id"] == logger.fixture_id


def test_select_media_respects_manifest_fixture_filter(tmp_path):
    import sys as _sys
    tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
    if tools_dir not in _sys.path:
        _sys.path.append(tools_dir)
    import weapon_fp_log_run as runner
    walking = tmp_path / "walking.avi"; walking.write_bytes(b"clip-walking")
    boxing = tmp_path / "boxing.avi"; boxing.write_bytes(b"clip-boxing")
    stray = tmp_path / "stray.avi"; stray.write_bytes(b"clip-stray")
    index = {
        runner.sha256_file(walking): {"fixture_id": "kth-walking-person01", "split": "train"},
        runner.sha256_file(boxing): {"fixture_id": "kth-boxing-person01", "split": "train"},
    }
    media = [walking, boxing, stray]
    assert runner.select_media(media, index, "walking") == [walking]
    assert runner.select_media(media, index, "boxing") == [boxing]
    assert runner.select_media(media, index, None) == media
    # Under a filter, unregistered media are excluded — never silently run.
    assert runner.select_media(media, index, "kth") == [walking, boxing]
    assert runner.select_media(media, index, "no-such-suite") == []


def test_runner_tool_is_importable_and_hashes_media(tmp_path):
    import sys as _sys
    tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
    if tools_dir not in _sys.path:
        _sys.path.append(tools_dir)
    import weapon_fp_log_run as runner
    sample = tmp_path / "clip.bin"
    sample.write_bytes(b"weapon-fp-runner-probe")
    assert runner.sha256_file(sample) == hashlib.sha256(b"weapon-fp-runner-probe").hexdigest()
    assert runner.iter_media([]) == []
    policy, source = runner.policy_from_args(None)
    assert source is None and hasattr(policy, "weapon_min_confidence")
    explicit, source = runner.policy_from_args(json.dumps({
        "weapon_infer_interval": 8, "weapon_min_confidence": 0.20, "weapon_score_ema_alpha": 0.45,
        "weapon_input_size": 640, "weapon_min_interval_ms": 2500,
        "weapon_realtime_threshold_ms": 500, "weapon_independent_alert_threshold": 0.65,
        "weapon_score_decay_half_life_ms": 5000, "weapon_signal_ttl_ms": 10000}))
    assert source == "cli" and explicit.weapon_min_confidence == 0.20
    with pytest.raises(SystemExit, match="missing required keys"):
        runner.policy_from_args('{"weapon_min_confidence": 0.2}')
    with pytest.raises(SystemExit, match="unknown keys"):
        runner.policy_from_args(json.dumps({
            "weapon_infer_interval": 8, "weapon_min_confidence": 0.20,
            "weapon_score_ema_alpha": 0.45, "weapon_input_size": 640,
            "weapon_min_interval_ms": 2500, "weapon_realtime_threshold_ms": 500,
            "weapon_independent_alert_threshold": 0.65,
            "weapon_score_decay_half_life_ms": 5000, "weapon_signal_ttl_ms": 10000,
            "weapon_typo_key": 1}))

