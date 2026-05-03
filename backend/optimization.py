"""
optimization.py — AI Sentinel Performance Optimizations
======================================================
"""

import cv2
import numpy as np
import threading
from typing import Tuple, Dict

# Cache for resized frames to avoid redundant resizing
_frame_cache: Dict[Tuple[int, int], np.ndarray] = {}
_frame_cache_lock = threading.Lock()

def cached_resize(frame: np.ndarray, size: int) -> np.ndarray:
    """Resize frame with caching based on frame content hash."""
    # Using a simple hash for demonstration; in production use a faster method if needed
    frame_hash = hash(frame.tobytes())
    cache_key = (frame_hash, size)
    
    with _frame_cache_lock:
        if cache_key in _frame_cache:
            return _frame_cache[cache_key]
    
    resized = cv2.resize(frame, (size, size), interpolation=cv2.INTER_LINEAR)
    
    with _frame_cache_lock:
        if len(_frame_cache) > 300:  # Limit cache size
            _frame_cache.clear()
        _frame_cache[cache_key] = resized
    
    return resized
