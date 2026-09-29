import time
import numpy as np
import pytest
WINDOW_SIZE = 32 # Constant from inference contract

@pytest.fixture
def pipeline():
    from inference import ViolenceInferencePipeline
    # Mock pipeline with dummy weights
    import torch
    device = torch.device("cpu")
    pipeline = ViolenceInferencePipeline.__new__(ViolenceInferencePipeline)
    pipeline.device = device
    pipeline.threshold = 0.75
    pipeline.stride = 16
    pipeline.is_x3d = False
    pipeline.enabled = True
    pipeline.disabled_reason = ""
    pipeline._inference_running = False
    pipeline._inference_lock = __import__('threading').Lock()
    pipeline.model = None
    pipeline._buffer = __import__('collections').deque(maxlen=WINDOW_SIZE)
    pipeline._last_label = 0
    pipeline._last_conf = 0.0
    pipeline._last_raw_conf = 0.0
    pipeline._last_calibrated_conf = 0.0
    pipeline._is_violent = False
    pipeline._counter = 0
    pipeline._ema_alpha = 0.45
    pipeline._hysteresis_margin = 0.08
    pipeline._logit_temp = 1.0
    pipeline._logit_bias = 0.0
    return pipeline

@pytest.mark.integration
def test_inference_latency_under_500ms(pipeline):
    """Inference should complete within 500ms for real-time performance."""
    dummy_frames = [np.random.randint(0, 255, (160, 160, 3), dtype=np.uint8) for _ in range(WINDOW_SIZE)]
    
    start = time.perf_counter()
    # Simulate the inference call
    pipeline._buffer.extend(dummy_frames)
    pipeline._counter = WINDOW_SIZE
    # Call process_frame which triggers inference
    result = pipeline.process_frame(dummy_frames[0])
    elapsed = (time.perf_counter() - start) * 1000
    
    assert elapsed < 500, f"Inference took {elapsed:.1f}ms, should be under 500ms"

@pytest.mark.integration
def test_stride_processing_does_not_block(pipeline):
    """Processing should not block the main capture loop."""
    import threading
    
    pipeline._buffer.extend([np.zeros((160, 160, 3), dtype=np.uint8) for _ in range(WINDOW_SIZE)])
    pipeline._counter = WINDOW_SIZE + 1
    
    # Simulate rapid frame processing
    times = []
    for i in range(10):
        start = time.perf_counter()
        pipeline.process_frame(np.zeros((160, 160, 3), dtype=np.uint8))
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    assert avg_time < 50, f"Average frame processing took {avg_time:.1f}ms, should be under 50ms"
