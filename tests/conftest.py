"""Shared pytest setup for the S-04 tracking/counting slice (WT-22).

Backend modules are imported as top-level modules (``from tracking import ...``),
matching how ``inference_process.py`` imports ``person_detector``.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
