"""Compatibility shim for legacy pipeline_ai imports.

The multiprocessing pipeline moved motion estimation into
``inference_process.py``. Keep this tiny re-export so older tests and
scripts continue to work while the rest of the pipeline uses the newer
module layout.
"""

from inference_process import estimate_motion_score

__all__ = ["estimate_motion_score"]
