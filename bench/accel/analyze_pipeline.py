"""Compare EXP-03 matched full-pipeline trials (WT-16).

Reads the run.py reports for the CPU-EP and CUDA-EP configurations, extracts
per-model completed-inference stage distributions and FPS bins, computes
CPU->CUDA ratios, checks the dirty-checkout claim band (pre-declared in
docs/campaign/experiments/03-full-pipeline-matched.md), and compares against
the registered revision-`6fb3bcac…` baseline at the same source hash.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STAGES = ("person_onnx", "weapon_window", "violence_window")
FPS_KEYS = ("capture_fps", "render_fps", "client_fps")
# Pre-declared claim band: dirty checkout claimed person 24.0/25.7 ms and weapon 43.0/40.3 ms.
CLAIM = {
    "person_onnx": {"low": 16.8, "high": 34.4, "claim": [24.0, 25.7]},
    "weapon_window": {"low": 28.2, "high": 55.9, "claim": [43.0, 40.3]},
    "capture_fps_p50_min": 28.0,
}
REGISTERED = Path(__file__).resolve().parents[2] / "bench/results/sprint2-verified-480p/report.json"


def load_run(directory: Path) -> dict:
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    summary = report.get("summary") or {}
    out = {"directory": str(directory), "seconds": report.get("seconds"),
           "warmup": report.get("warmup_seconds"), "workload_valid": report.get("workload_valid"),
           "runtime_exit_code": report.get("runtime_exit_code"),
           "source": ((report.get("environment") or {}).get("source") or {}),
           "models": summary.get("models")}
    for stage in STAGES:
        out[stage] = (summary.get("stage_latency_ms") or {}).get(stage)
    for key in FPS_KEYS:
        value = summary.get(key) or {}
        out[key] = {k: value.get(k) for k in ("count", "p05", "p50", "p95", "max")}
    out["model_call_counts"] = summary.get("model_call_counts")
    out["ipc_dropped_frames"] = summary.get("ipc_dropped_frames")
    return out


def medians(runs: list[dict]) -> dict:
    out = {}
    for stage in (*STAGES, *FPS_KEYS):
        values = [run[stage]["p50"] for run in runs if run.get(stage) and run[stage].get("p50") is not None]
        out[stage] = {"n_runs": len(values), "medianOfP50": sorted(values)[len(values) // 2] if values else None,
                      "perRun": values}
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path,
                        default=Path(__file__).resolve().parents[2] / "bench/results/campaign-accel-2026-09-29")
    args = parser.parse_args()
    cpu_runs = [load_run(args.results / f"fullpipeline-cpu-{n}") for n in (1, 2)]
    cuda_runs = [load_run(args.results / f"fullpipeline-cuda-{n}") for n in (1, 2)]
    cpu_sum, cuda_sum = medians(cpu_runs), medians(cuda_runs)
    ratios = {}
    for stage in STAGES:
        cpu, cuda = cpu_sum[stage]["medianOfP50"], cuda_sum[stage]["medianOfP50"]
        ratios[stage] = round(cpu / cuda, 3) if cpu and cuda else None
    claim_checks = {}
    for stage, band in CLAIM.items():
        if stage == "capture_fps_p50_min":
            continue
        values = [cuda_sum[stage]["medianOfP50"]]
        claim_checks[stage] = {"cudaP50PerRun": cuda_sum[stage]["perRun"],
                               "inClaimBand": [v is not None and band["low"] <= v <= band["high"] for v in values],
                               "claimValues": band["claim"], "band": [band["low"], band["high"]]}
    capture_ok = all(run.get("capture_fps", {}).get("p50", 0) >= CLAIM["capture_fps_p50_min"]
                     for run in cuda_runs)
    in_band = [all(flag for flag in entry["inClaimBand"]) for entry in claim_checks.values()]
    if all(in_band) and capture_ok:
        claim_verdict = "REPRODUCED"
    elif sum(in_band) >= 1 or capture_ok:
        claim_verdict = "PARTIAL"
    else:
        claim_verdict = "REFUTED"
    registered = json.loads(REGISTERED.read_text(encoding="utf-8")) if REGISTERED.exists() else None
    registered_block = None
    if registered:
        registered_block = {"revision": (registered.get("environment") or {}).get("revision"),
                            "source": ((registered.get("environment") or {}).get("source") or {}),
                            "stages": {stage: (registered["summary"]["stage_latency_ms"] or {}).get(stage)
                                       for stage in STAGES},
                            "capture_fps": (registered["summary"].get("capture_fps") or {}).get("p50")}
    result = {
        "experiment": "EXP-03 pipeline comparison",
        "cpuRuns": cpu_runs, "cudaRuns": cuda_runs,
        "cpuMedians": cpu_sum, "cudaMedians": cuda_sum,
        "cpuToCudaSpeedup": ratios,
        "speedGate": {stage: (ratio is not None and ratio >= 1.5) for stage, ratio in ratios.items()},
        "dirtyClaimCheck": {"claim": CLAIM, "perStage": claim_checks,
                            "captureFpsAtLeast28BothRuns": capture_ok, "verdict": claim_verdict},
        "registeredBaseline": registered_block,
        "clockBase": "perf_counter",
    }
    out = args.results / "raw" / "raw-pipeline-comparison.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"comparison": str(out), "cpuMedians": cpu_sum, "cudaMedians": cuda_sum,
                      "speedups": ratios, "claimVerdict": claim_verdict, "captureOk": capture_ok}, indent=2))


if __name__ == "__main__":
    main()
