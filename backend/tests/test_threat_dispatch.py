import pytest
import time
from unittest.mock import MagicMock, patch

@patch("backend.api.fusion_engine")
@patch("backend.api.weapon_engine")
def test_weapon_only_triggers_alert(mock_weapon_engine, mock_fusion):
    # Setup
    mock_pipeline = MagicMock()
    mock_pipeline._is_violent = False
    mock_pipeline._last_conf = 0.1
    
    mock_weapon_signal = {"ready": True, "labels": ["handgun"]}
    
    # Mock weapon engine
    mock_weapon_engine.config.independent_alert_threshold = 0.65
    
    # Mock fusion engine
    mock_fusion.config.weapon_threshold = 0.55
    mock_fusion.assess.return_value = {
        "score": 85.0,
        "severity": "high",
        "model": "fusion-v1",
        "motionScore": 0.1,
        "weaponScore": 80.0,
        "reason": "Weapon detected"
    }
    
    from backend.api import _generate_alert_payload
    
    payload = _generate_alert_payload(
        alert_id="test-123",
        pipeline=mock_pipeline,
        weapon_score=0.8,
        weapon_signal=mock_weapon_signal,
        motion_score=0.1,
        face_summary={},
        cam_id="CAM-01",
        now=time.time(),
        t0=time.perf_counter()
    )
    
    assert payload["threatType"] == "weapon"
    assert "Weapon Detection" in payload["type"]
    assert payload["confidence"] == 85.0

@patch("backend.api.fusion_engine")
@patch("backend.api.weapon_engine")
def test_violence_triggers_alert(mock_weapon_engine, mock_fusion):
    # Setup
    mock_pipeline = MagicMock()
    mock_pipeline._is_violent = True
    mock_pipeline._last_conf = 0.85
    
    mock_weapon_signal = {"ready": True, "labels": []}
    
    # Mock weapon engine
    mock_weapon_engine.config.independent_alert_threshold = 0.65
    
    # Mock fusion engine
    mock_fusion.assess.return_value = {
        "score": 88.0,
        "severity": "critical",
        "model": "fusion-v1",
        "motionScore": 0.1,
        "weaponScore": 0.0,
        "reason": "Violence detected"
    }
    
    from backend.api import _generate_alert_payload
    
    payload = _generate_alert_payload(
        alert_id="test-456",
        pipeline=mock_pipeline,
        weapon_score=0.1,
        weapon_signal=mock_weapon_signal,
        motion_score=0.1,
        face_summary={},
        cam_id="CAM-01",
        now=time.time(),
        t0=time.perf_counter(),
        decision_result={"confirmed_alert": True, "alert_state": "CONFIRMED_VIOLENCE"}
    )
    
    assert payload["threatType"] == "violence"
    assert "Violence" in payload["type"]
    assert payload["confidence"] == 88.0
