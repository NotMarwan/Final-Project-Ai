"""Assemble bench/results/campaign-accel-2026-09-29/report.json (WT-16).

report.json carries: environment (code SHA, packages, GPU), model hashes,
preprocessing/decision config facts, adapter state (B-3 disclosure), clock
discipline, and the SHA-256 of every raw artifact produced by the campaign
runs. Verdicts are cross-referenced to the EXP cards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RESULTS = ROOT / "bench/results/campaign-accel-2026-09-29"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def model_hashes() -> dict:
    models = {
        "person_yolo.onnx": Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/models/person_yolo.onnx"),
        "weapon_yolo.onnx": Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/models/weapon_yolo.onnx"),
        "best_model.pt": Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/best_model.pt"),
        "weapon_hadi_yolo.pt": Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/weapon_hadi_yolo.pt"),
    }
    result = {}
    for label, path in models.items():
        result[label] = ({"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
                         if path.exists() else {"path": str(path), "missing": True})
    return result


def environment() -> dict:
    from importlib.metadata import PackageNotFoundError, version
    packages = {}
    for package in ("torch", "onnxruntime", "onnxruntime-gpu", "numpy", "opencv-python", "ultralytics"):
        try:
            packages[package] = version(package)
        except PackageNotFoundError:
            packages[package] = None
    import onnxruntime as ort
    import torch
    return {
        "python": sys.version,
        "packages": packages,
        "ortAvailableProviders": ort.get_available_providers(),
        "torchCuda": torch.version.cuda,
        "torchCudnn": torch.backends.cudnn.version() if torch.backends.cudnn.is_available() else None,
        "gitHead": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                  text=True, check=True).stdout.strip(),
        "gitBranch": subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True,
                                    text=True, check=True).stdout.strip(),
        "gpu": subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                               "--format=csv,noheader"], capture_output=True, text=True,
                              check=True).stdout.strip(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verdicts", type=Path, default=None,
                        help="JSON file with {expId: {verdict, notes}} entries")
    args = parser.parse_args()
    raw_dir = RESULTS / "raw"
    artifacts = {}
    for path in sorted(RESULTS.rglob("*")):
        if path.is_file() and path.name != "report.json":
            artifacts[str(path.relative_to(RESULTS))] = {"sha256": sha256(path), "bytes": path.stat().st_size}
    verdicts = json.loads(args.verdicts.read_text(encoding="utf-8")) if args.verdicts else {}
    report = {
        "schema": "sentinel-accel-report/1",
        "campaign": "WT-16 inference acceleration (S-20 slice: provider/session/precision/export)",
        "worktree": str(ROOT),
        "environment": environment(),
        "modelHashes": model_hashes(),
        "preprocessing": "yolo_onnx.prepare_input: letterbox max-side to fixed model input, pad 114, BGR->RGB, /255, NCHW float32",
        "decisionConfig": "config/thresholds.toml defaults untouched (violence 0.45, weapon 0.55, display 0.45)",
        "sourceMode": "file-media for every fixture and full-pipeline run (no camera device exists); no run is labeled live",
        "fixtureProvenance": "Full-pipeline trials read the demo asset READ-ONLY from the user's pre-existing worktree "
                            "C:/Users/PCD/Downloads/jobs/integration/demo_assets/videos/Wq0BuA8GM84_0.avi "
                            "(sha256 55ff3f5731ab5d1001325786593b02102dc137c87b6051905f4e6932c22ad586; identical to the "
                            "registered revision-6fb3bcac run's source). Microbench/parity fixtures read cam3.mp4 "
                            "(sha256 recorded per artifact) from the primary checkout, also read-only. Nothing was "
                            "written into either source location.",
        "adapterState": {
            "B3": "bench harness auto-stubs go2rtc_bridge/openrouter_reporting (modules absent); SC-10 optional-import "
                  "commit cherry-picked as 86d7697 so api.py is importable in a clean checkout; every measurement ran "
                  "with the harness stub adapters active and benchmark-overrides.json recorded",
        },
        "clockBase": "perf_counter",
        "clockDiscipline": "all durations single-clock perf_counter_ns diffs; producer monotonic stamps copied through "
                           "unchanged and never subtracted across bases; processing latency is not glass-to-alert",
        "measurementRules": "completed-inference timing (CUDA synchronized where applicable); cold vs warm separated; "
                            "p05/p50/p95/max with counts; launch timings never mixed into compute distributions",
        "artifacts": artifacts,
        "experimentVerdicts": verdicts,
        "limitations": [
            "venv shared and read-only: no wheel switch executed (pip show onnxruntime-gpu unchanged at end); "
            "promotion delivered as operator-executable flow with switch-mechanics tests",
            "camera device absent: live-capture integrity unproven everywhere",
            "fp16 mixed-precision (head block-listed) deferred: onnxconverter_common absent, venv read-only",
        ],
    }
    path = RESULTS / "report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(path), "artifacts": len(artifacts)}, indent=2))


if __name__ == "__main__":
    main()
