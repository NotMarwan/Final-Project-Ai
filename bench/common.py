from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def distribution(values):
    values = sorted(float(x) for x in values)
    if not values:
        return {"count": 0, "p05": None, "p50": None, "p95": None, "max": None}
    if not all(math.isfinite(x) for x in values):
        raise ValueError("Measurements must be finite")

    def percentile(q):
        position = (len(values) - 1) * q
        low = int(position)
        high = min(low + 1, len(values) - 1)
        return round(values[low] + (values[high] - values[low]) * (position - low), 6)

    return {"count": len(values), "p05": percentile(.05), "p50": percentile(.5),
            "p95": percentile(.95), "max": values[-1]}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def command(args):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30, check=True).stdout.strip()


def environment():
    packages = {}
    for package in ("torch", "torchvision", "ultralytics", "onnxruntime", "onnxruntime-gpu", "opencv-python", "numpy", "fastapi", "pytest", "httpx", "psutil"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    result = {"python": sys.version, "platform": platform.platform(), "packages": packages,
              "revision": command(["git", "rev-parse", "HEAD"]),
              "branch": command(["git", "branch", "--show-current"])}
    try:
        result["gpu"] = command(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])
    except (subprocess.SubprocessError, OSError) as exc:
        result["gpu"] = {"error": type(exc).__name__}
    result["source_hashes"] = {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(BACKEND.rglob("*.py")) if not {"tests", "tools", "archive", "__pycache__", "احتياطي"}.intersection(p.relative_to(BACKEND).parts)}
    return result


def prepare_environment():
    """Use detection settings only. Do not import live notification credentials."""
    import dotenv
    settings = dotenv.dotenv_values(BACKEND / ".env")
    prefixes = ("VIOLENCE_", "WEAPON_", "PERSON_", "AI_SENTINEL_WATCH_", "AI_SENTINEL_CONFIRM_", "AI_SENTINEL_MIN_DECISION_", "AI_SENTINEL_ALERT_COOLDOWN_")
    exact = {"THRESHOLD", "STRIDE", "WEIGHTS_PATH", "STREAM_QUALITY"}
    selected = {k: v for k, v in settings.items() if v is not None and (k in exact or k.startswith(prefixes))}
    os.environ.update(selected)
    for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        os.environ[key] = ""
    os.environ["AI_SENTINEL_ENABLE_CAPTURE_LOOP"] = "false"
    os.environ["TELEGRAM_ENABLED"] = "false"
    os.environ["PYTHONUTF8"] = "1"
    dotenv.load_dotenv = lambda *args, **kwargs: False
    sys.path.insert(0, str(BACKEND))
    return selected


def clip_metrics(records):
    """Only explicitly verified labels count; unknown clips remain unevaluated."""
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "unevaluated": 0}
    for row in records:
        if row.get("label") not in ("positive", "negative") or not row.get("label_verified") or row.get("completed") is not True:
            counts["unevaluated"] += 1
            continue
        key = ("tp" if row["alert_count"] else "fn") if row["label"] == "positive" else ("fp" if row["alert_count"] else "tn")
        counts[key] += 1
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    return {**counts, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None}
