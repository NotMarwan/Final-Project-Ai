# Threat Latency Benchmark Harness

This tool provides a repeatable, data-driven framework for measuring detection-to-alert latency in the AI Sentinel system.

## Purpose
- Measure P50/P95 latency for violence and weapon detection.
- Validate performance impact of architectural changes (e.g., stride, threading).
- Compare theoretical performance across different metadata-labeled configurations.

## Current Baseline (CPU)
Measurements taken on the development machine (CPU) are **baseline measurements only**. 

| Angle Label | P95 Detection Latency | P95 Weapon Inference |
| :--- | :--- | :--- |
| High CCTV | ~3.7s | ~3.9s |
| Eye-Level | ~4.3s | ~5.1s |

> [!IMPORTANT]
> **Limitations & Disclaimer**
> 1. **Angle Comparison**: The current numbers do **not** prove real-world 3.5m vs 170cm camera-angle performance improvement. Both runs utilized the same source video (`backend/cam1.mp4`) as a smoke test. Real angle comparison requires recording separate videos from those specific heights.
> 2. **GPU Performance**: Sub-500ms latency on GPU is **not proven**. GPU performance must be measured later on the exhibition laptop. Any claims of sub-500ms performance are currently unverified hypotheses.
> 3. **Hardware**: These numbers are highly dependent on host CPU load and are intended for relative comparison during local development.

## Usage
Run the benchmark without saving to disk:
```powershell
$env:PYTHONPATH="backend"
python backend/tools/benchmark_threat_latency.py --video backend/cam1.mp4 --iterations 20
```

Generate a JSON report:
```powershell
python backend/tools/benchmark_threat_latency.py --video backend/cam1.mp4 --output results.json
```

## Metrics Tracked
- **Detection Latency**: Time from frame ingestion to threat confirmation.
- **Alert Dispatch**: Simulated overhead for internal alert routing.
- **Weapon Inference**: Specific latency for the weapon detection engine.
- **Total Overhead**: Full processing time per frame.
