from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def resolve_calibration_path(raw_path: str | None = None, base_dir: Path | None = None) -> Path:
    root = base_dir or Path(__file__).resolve().parent
    candidate = raw_path or os.getenv("MODEL_CALIBRATION_PATH", "model_calibration.json")
    path = Path(candidate)
    return path if path.is_absolute() else (root / path)


def load_calibration_profile(raw_path: str | None = None, base_dir: Path | None = None) -> dict[str, Any]:
    path = resolve_calibration_path(raw_path=raw_path, base_dir=base_dir)
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
