import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch
import numpy as np
import cv2

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.benchmark_threat_latency import run_benchmark

def test_benchmark_stats_calculation():
    """Test that statistics are calculated correctly with dummy data."""
    with patch('os.path.exists', return_value=True), \
         patch('cv2.VideoCapture') as mock_cap, \
         patch('inference.ViolenceInferencePipeline') as mock_v, \
         patch('weapon.WeaponSignalEngine') as mock_w, \
         patch('fusion.ThreatFusionEngine') as mock_f:
            
        mock_instance = mock_cap.return_value
        mock_instance.isOpened.return_value = True
        mock_instance.get.side_effect = lambda p: 10.0 if p == cv2.CAP_PROP_FRAME_COUNT else 30.0
        mock_instance.read.side_effect = [
            (True, np.zeros((100, 100, 3), dtype=np.uint8)) for _ in range(10)
        ] + [(False, None)]
        
        mock_v_instance = mock_v.return_value
        mock_v_instance.process_frame.return_value = np.zeros((100, 100, 3))
        mock_v_instance._is_violent = False
        mock_v_instance._inference_running = False
        mock_v_instance._inference_lock = MagicMock()
        
        mock_w_instance = mock_w.return_value
        mock_w_instance.process_frame.return_value = {"score": 0.1}
        mock_w_instance.config.independent_alert_threshold = 0.65
        mock_w_instance._inference_running = False
        mock_w_instance._lock = MagicMock()
        mock_w_instance._last_score = 0.1
        mock_w_instance._last_inference_latency_ms = 10.0
        
        report = run_benchmark("fake_video.mp4", iterations=10)
        
        assert report is not None
        assert report["summary"]["total_frames"] == 10
        assert "latencies_ms" in report

def test_benchmark_threat_detection():
    """Test that detection latency is recorded when a threat is found."""
    with patch('os.path.exists', return_value=True), \
         patch('cv2.VideoCapture') as mock_cap, \
         patch('inference.ViolenceInferencePipeline') as mock_v, \
         patch('weapon.WeaponSignalEngine') as mock_w, \
         patch('fusion.ThreatFusionEngine') as mock_f:
            
        mock_cap_instance = mock_cap.return_value
        mock_cap_instance.isOpened.return_value = True
        mock_cap_instance.get.side_effect = lambda p: 5.0 if p == cv2.CAP_PROP_FRAME_COUNT else 30.0
        mock_cap_instance.read.side_effect = [
            (True, np.zeros((100, 100, 3), dtype=np.uint8)) for _ in range(5)
        ] + [(False, None)]
        
        mock_v_instance = mock_v.return_value
        mock_v_instance._is_violent = True # Always violent for this test
        mock_v_instance._inference_running = False
        mock_v_instance._inference_lock = MagicMock()
        
        mock_w_instance = mock_w.return_value
        mock_w_instance.config.independent_alert_threshold = 0.65
        mock_w_instance.process_frame.return_value = {"score": 0.0}
        mock_w_instance._inference_running = False
        mock_w_instance._lock = MagicMock()
        mock_w_instance._last_score = 0.0
        mock_w_instance._last_inference_latency_ms = 5.0
        
        report = run_benchmark("fake_video.mp4", iterations=5)
        
        assert report["summary"]["threats_detected"] == 5
        assert report["latencies_ms"]["detection"]["avg"] > 0
