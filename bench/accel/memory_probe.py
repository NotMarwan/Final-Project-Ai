"""Per-camera-process VRAM measurement (WT-16, EXP-06).

Production shape: one spawned inference process per camera, each owning
violence (torch) + weapon + person (ONNX). Measured at 1 and 2 workers on one
RTX 3060 (12 GB):

- `nvidia-smi --query-compute-apps=pid,used_memory` per worker pid — the honest
  per-process figure (covers CUDA context + ORT CUDA arena + torch).
- `torch.cuda.max_memory_allocated()` inside the worker — torch allocator only;
  it does NOT see ORT allocations. Both are reported, each labeled.
- RSS per worker (system RAM matters: 16 GB shared with the dashboard).

Counters are per processRunId (uuid4) + workerPid per the WT-13 schema.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DEFAULT_PERSON = Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/models/person_yolo.onnx")
DEFAULT_WEAPON = Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/models/weapon_yolo.onnx")
DEFAULT_VIOLENCE = Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/best_model.pt")


def _nvidia_smi_compute_apps() -> list[dict]:
    completed = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=30)
    rows = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            rows.append({"pid": int(parts[0]), "processName": parts[1], "gpuMemoryUsedMB": float(parts[2])})
    return rows


def _nvidia_smi_total_used_mb() -> float:
    completed = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=30)
    return float(completed.stdout.strip().splitlines()[0])


def worker(ready_queue, result_queue, stop_event, models: str, person_path: str, weapon_path: str,
           violence_path: str) -> None:
    process_run_id = str(uuid.uuid4())
    report = {"processRunId": process_run_id, "workerPid": os.getpid(), "models": models.split(",")}
    import torch
    import yolo_onnx
    from bench.accel.harness import build_session

    sessions = {}
    if "person" in report["models"]:
        sessions["person"], _, person_load_ms = build_session(Path(person_path), "cuda")
        report["personLoadMs"] = round(person_load_ms, 3)
    if "weapon" in report["models"]:
        sessions["weapon"], _, weapon_load_ms = build_session(Path(weapon_path), "cuda")
        report["weaponLoadMs"] = round(weapon_load_ms, 3)
    if "violence" in report["models"]:
        from inference import ViolenceInferencePipeline
        started = time.perf_counter()
        pipeline = ViolenceInferencePipeline(violence_path, torch.device("cuda"))
        report["violenceLoadMs"] = round((time.perf_counter() - started) * 1000, 3)
        report["violenceModelClass"] = type(pipeline.model).__name__ if pipeline.model is not None else None
    # Warm allocations: 3 completed inferences per session so arenas reach steady size.
    if sessions:
        from bench.accel.fixtures import load_frames
        frames, _fixture = load_frames()
        frame = frames[0]
        width, height = yolo_onnx.model_input_size(next(iter(sessions.values())).get_inputs()[0].shape)
        tensor, _transform = yolo_onnx.prepare_input(frame, (width, height))
        for label, session in sessions.items():
            name = session.get_inputs()[0].name
            outputs = [output.name for output in session.get_outputs()]
            for _ in range(3):
                session.run(outputs, {name: tensor})
            report.setdefault("warmCompletedCount", {})[label] = 3
    if "violence" in report["models"] and report.get("violenceModelClass"):
        report["violenceWarmNote"] = ("model constructed and moved to cuda:0; window forward pass not "
                                      "run in this probe (VRAM of weights + context + lazy workspace)")
    torch.cuda.synchronize()
    report["torchMaxMemoryAllocatedBytes"] = int(torch.cuda.max_memory_allocated())
    report["torchMaxMemoryReservedBytes"] = int(torch.cuda.max_memory_reserved())
    ready_queue.put(report)
    stop_event.wait(timeout=600)
    result_queue.put(report)


def measure(workers: int, models: str, person_path: Path, weapon_path: Path, violence_path: Path,
            out_dir: Path) -> dict:
    ctx = mp.get_context("spawn")
    ready_queue, result_queue, stop_event = ctx.Queue(), ctx.Queue(), ctx.Event()
    baseline_mb = _nvidia_smi_total_used_mb()
    processes = []
    started = time.perf_counter()
    for _ in range(workers):
        process = ctx.Process(target=worker,
                              args=(ready_queue, result_queue, stop_event, models,
                                    str(person_path), str(weapon_path), str(violence_path)))
        process.start()
        processes.append(process)
    worker_reports = [ready_queue.get(timeout=300) for _ in range(workers)]
    time.sleep(2.0)  # let lazy allocations settle
    compute_apps = _nvidia_smi_compute_apps()
    pids = {report["workerPid"] for report in worker_reports}
    per_process = [row for row in compute_apps if row["pid"] in pids]
    total_used_after_mb = _nvidia_smi_total_used_mb()
    rss = {}
    try:
        import psutil
        for pid in pids:
            rss[str(pid)] = int(psutil.Process(pid).memory_info().rss)
    except Exception as exc:  # noqa: BLE001 - recorded, not fatal
        rss = {"error": type(exc).__name__}
    stop_event.set()
    for process in processes:
        process.join(timeout=60)
        if process.is_alive():
            process.terminate()
    result = {
        "experiment": f"vram-{workers}-worker" + ("-trio" if "violence" in models else "-onnx"),
        "workers": workers,
        "models": models.split(","),
        "gpuBaselineUsedMB": baseline_mb,
        "gpuTotalUsedAfterMB": total_used_after_mb,
        "gpuPerProcessNvidiaSmi": per_process,
        "gpuPerProcessSumMB": round(sum(row["gpuMemoryUsedMB"] for row in per_process), 1),
        "workerReports": worker_reports,
        "processRssBytes": rss,
        "resourceSamplerSource": "nvidia-smi --query-compute-apps (per pid) + torch.cuda.max_memory_* (worker, torch allocator only)",
        "wallClockSeconds": round(time.perf_counter() - started, 3),
        "clockBase": "perf_counter",
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw-vram-{workers}w-{models.replace(',', '-')}.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    result["rawPath"] = str(path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, choices=(1, 2), required=True)
    parser.add_argument("--models", default="person,weapon",
                        help="comma list of person,weapon,violence")
    parser.add_argument("--person-model", type=Path, default=DEFAULT_PERSON)
    parser.add_argument("--weapon-model", type=Path, default=DEFAULT_WEAPON)
    parser.add_argument("--violence-model", type=Path, default=DEFAULT_VIOLENCE)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[2] / "bench/results/campaign-accel-2026-09-29/raw")
    args = parser.parse_args()
    allowed = {"person", "weapon", "violence"}
    models = [model.strip() for model in args.models.split(",") if model.strip()]
    if not models or not set(models) <= allowed:
        parser.error(f"--models must be a nonempty subset of {sorted(allowed)}")
    result = measure(args.workers, ",".join(models), args.person_model.resolve(),
                     args.weapon_model.resolve(), args.violence_model.resolve(), args.out)
    print(json.dumps({key: result[key] for key in
                      ("experiment", "workers", "gpuBaselineUsedMB", "gpuTotalUsedAfterMB",
                       "gpuPerProcessSumMB", "rawPath")}, indent=2))


if __name__ == "__main__":
    main()
