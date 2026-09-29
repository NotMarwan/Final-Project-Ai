"""Frame resizing without identity- or mutable-output-based cache reuse."""
import cv2
import numpy as np


def cached_resize(frame: np.ndarray, size: int) -> np.ndarray:
    """Resize the current pixels; camera buffers and returned arrays are mutable.

    Kept under its existing name for callers. Caching entire mutable arrays can
    return stale input or caller-modified output, and retains substantial RAM.
    """
    return cv2.resize(frame, (size, size), interpolation=cv2.INTER_LINEAR)
