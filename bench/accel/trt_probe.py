"""TensorRT EP availability probe (WT-16, EXP-05 stage-2 gate).

The installed onnxruntime-gpu 1.18.0 wheel LISTS TensorrtExecutionProvider,
but the TRT 10.0 runtime libraries must exist on the host for it to work
(WT-09 section 6 pitfall 6). This probe turns "listed" into a measured
session-creation outcome and, if TRT works, budgets the first engine build
against the G-13 cold-start budget (60 s) and the cached-session time.

Engine cache: a hashed directory outside the repo. Documented invalidation
triggers (ORT TRT EP docs): model change, ORT version change, TensorRT version
change, hardware change. The cache is disposable and never authoritative.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SCRATCH = Path("C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-16-artifacts/trt-engine-cache")
G13_BUDGET_SECONDS = 60.0


def cache_dir_for(model_path: Path, ort_version: str, gpu_name: str) -> Path:
    import onnxruntime as ort  # noqa: F401
    key = hashlib.sha256()
    with model_path.open("rb") as stream:
        key.update(hashlib.file_digest(stream, "sha256").digest())
    key.update(ort_version.encode())
    key.update(gpu_name.encode())
    return SCRATCH / key.hexdigest()[:16]


def gpu_name() -> str:
    import subprocess
    completed = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                               capture_output=True, text=True, timeout=30)
    return completed.stdout.strip()


def probe(model_path: Path, out_dir: Path) -> dict:
    import onnxruntime as ort
    import yolo_onnx
    name = gpu_name()
    engine_cache = cache_dir_for(model_path, ort.__version__, name)
    engine_cache.mkdir(parents=True, exist_ok=True)
    trt_options = {
        "trt_engine_cache_enable": "1",
        "trt_engine_cache_path": str(engine_cache),
        "trt_timing_cache_enable": "1",
        "trt_fp16_enable": "0",
    }
    result = {
        "experiment": "trt-ep-probe",
        "modelPath": str(model_path),
        "ortVersion": ort.__version__,
        "ortAvailableProviders": ort.get_available_providers(),
        "gpuName": name,
        "engineCacheDir": str(engine_cache),
        "engineCacheInvalidationTriggers": ["model change", "ORT version change",
                                            "TensorRT version change", "hardware change"],
        "trtOptions": trt_options,
        "g13BudgetSeconds": G13_BUDGET_SECONDS,
        "clockBase": "perf_counter",
    }
    providers = [("TensorrtExecutionProvider", trt_options),
                 ("CUDAExecutionProvider", dict(yolo_onnx.CUDA_PROVIDER_OPTIONS)),
                 "CPUExecutionProvider"]
    options = yolo_onnx.session_options(ort)
    started = time.perf_counter()
    try:
        session = ort.InferenceSession(str(model_path), sess_options=options, providers=providers)
    except Exception as exc:  # noqa: BLE001 - the failure signature is the evidence
        result.update({
            "sessionCreated": False,
            "failureSeconds": round(time.perf_counter() - started, 3),
            "failureType": type(exc).__name__,
            "failureMessage": str(exc)[:2000],
            "verdict": "TRT EP unavailable on this host at probe time; stage-2 not runnable",
        })
    else:
        active = session.get_providers()
        build_seconds = time.perf_counter() - started
        started_cached = time.perf_counter()
        try:
            second = ort.InferenceSession(str(model_path), sess_options=options, providers=providers)
            cached_seconds = time.perf_counter() - started_cached
            cached_active = second.get_providers()
        except Exception as exc:  # noqa: BLE001
            cached_seconds, cached_active = None, f"{type(exc).__name__}: {exc}"[:500]
        cache_files = [{"name": item.name, "bytes": item.stat().st_size}
                       for item in sorted(engine_cache.glob("*"))]
        result.update({
            "sessionCreated": True,
            "activeProviders": active,
            "firstSessionSeconds": round(build_seconds, 3),
            "firstSessionWithinG13": build_seconds <= G13_BUDGET_SECONDS,
            "cachedSessionSeconds": round(cached_seconds, 3) if cached_seconds is not None else None,
            "cachedSessionActiveProviders": cached_active,
            "engineCacheFiles": cache_files,
            "engineCacheBytes": sum(item["bytes"] for item in cache_files),
            "verdict": ("TRT EP worked; engine build vs G-13 budget recorded; promotion still gated on "
                        "EXP-01..03 parity/speed evidence"
                        if build_seconds <= G13_BUDGET_SECONDS else
                        "TRT EP worked but first engine build exceeds the G-13 cold-start budget"),
        })
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "raw-trt-probe.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    result["rawPath"] = str(path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path,
                        default=Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/models/person_yolo.onnx"))
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[2] / "bench/results/campaign-accel-2026-09-29/raw")
    args = parser.parse_args()
    result = probe(args.model.resolve(), args.out)
    print(json.dumps({key: result[key] for key in result
                      if key not in ("trtOptions", "failureMessage")} | (
                          {"failureMessage": result.get("failureMessage")} if "failureMessage" in result else {}),
                     indent=2))


if __name__ == "__main__":
    main()
