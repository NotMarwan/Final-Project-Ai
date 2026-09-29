import os
import sys
import pytest
from unittest.mock import MagicMock, patch
import numpy as np

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.run_multi_angle_benchmarks import run_bulk_benchmark

def test_bulk_benchmark_scanning():
    """Test that the bulk runner correctly scans a directory and calls run_benchmark."""
    with patch('os.listdir', return_value=['high_test.mp4', 'eye_level_test.mp4', 'not_a_video.txt']), \
         patch('os.path.join', side_effect=lambda a, b: f"{a}/{b}"), \
         patch('tools.benchmark_threat_latency.run_benchmark') as mock_run:
        
        mock_run.return_value = {
            'latencies_ms': {
                'detection': {'p95': 100},
                'weapon_inference': {'p95': 200}
            }
        }
        
        run_bulk_benchmark("dummy_dir", "dummy_weights.pt", iterations=10)
        
        # Should have called run_benchmark twice (for the two .mp4 files)
        assert mock_run.call_count == 2
        
        # Verify angle inference from filenames
        args1 = mock_run.call_args_list[0][1]
        assert args1['angle'] == "high"
        
        args2 = mock_run.call_args_list[1][1]
        assert args2['angle'] == "eye_level"

def test_bulk_benchmark_error_handling():
    """Test that the bulk runner continues if one video fails."""
    with patch('os.listdir', return_value=['v1.mp4', 'v2.mp4']), \
         patch('os.path.join', side_effect=lambda a, b: f"{a}/{b}"), \
         patch('tools.benchmark_threat_latency.run_benchmark') as mock_run:
        
        # First call fails, second succeeds
        mock_run.side_effect = [Exception("Test error"), {
            'latencies_ms': {
                'detection': {'p95': 100},
                'weapon_inference': {'p95': 200}
            }
        }]
        
        # This should not raise an exception
        run_bulk_benchmark("dummy_dir", "dummy_weights.pt")
        
        assert mock_run.call_count == 2
