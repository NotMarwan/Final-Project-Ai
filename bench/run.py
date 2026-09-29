"""One-command bounded baseline: original runtime, MJPEG + two SSE clients."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

from bench.common import ROOT, distribution, environment, sha256, write_json


async def observe(base, seconds, extended_controls=False):
    import httpx
    result = {"mjpeg_times": [], "sse_events": {}, "requests": [], "errors": []}
    async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=10), trust_env=False, headers={"x-api-key": "local-benchmark-only"}) as client:
        status = await client.get(base + "/system/status")
        status.raise_for_status()
        result["initial_status"] = status.json()
        threshold = status.json()["model"]["threshold"]
        control_cases = [("/set_threshold", {"threshold": threshold})]
        if extended_controls:
            policy_response = await client.get(base + "/decision/config", headers={"x-api-key": "local-benchmark-only"})
            policy_response.raise_for_status()
            policy = policy_response.json()["policy"]
            control_cases.extend([("/set_cooldown", {"cooldown": policy["cooldown_seconds"]}), ("/decision/config", policy)])
        result["control_workload"] = [route for route, _ in control_cases]

        async def stream(path, kind):
            try:
                async with client.stream("GET", base + path, timeout=None) as response:
                    response.raise_for_status()
                    if kind == "mjpeg":
                        buffer = b""
                        async for chunk in response.aiter_bytes():
                            buffer += chunk
                            while b"\xff\xd9\r\n" in buffer:
                                _, buffer = buffer.split(b"\xff\xd9\r\n", 1)
                                result["mjpeg_times"].append(time.perf_counter())
                            if len(buffer) > 20_000_000:
                                raise ValueError("MJPEG frame exceeds measurement limit")
                    else:
                        result["sse_events"][kind] = 0
                        async for line in response.aiter_lines():
                            if line.startswith("data:"):
                                result["sse_events"][kind] += 1
                                if kind == "alerts":
                                    try:
                                        payload = json.loads(line[5:].strip())
                                    except json.JSONDecodeError:
                                        continue
                                    if isinstance(payload, dict) and payload.get("id"):
                                        result.setdefault("alerts_received", []).append({
                                            "at": time.perf_counter(),
                                            "alert_id": payload["id"],
                                            "alertLatencyMs": payload.get("alertLatencyMs"),
                                        })
            except (httpx.HTTPError, ValueError) as exc:
                result["errors"].append({"stream": kind, "error": type(exc).__name__})

        async def controls():
            # Keep policy values unchanged so load testing does not tune the detector.
            for _ in range(100):
                for route, body in control_cases:
                    start = time.perf_counter()
                    try:
                        response = await client.post(base + route, json=body,
                                                     headers={"x-api-key": "local-benchmark-only"})
                        result["requests"].append({"route": route, "status": response.status_code,
                                                   "ms": (time.perf_counter() - start) * 1000})
                    except httpx.HTTPError as exc:
                        result["requests"].append({"route": route, "error": type(exc).__name__})
                await asyncio.sleep(.2)

        tasks = [asyncio.create_task(stream("/video_feed?camera_id=BENCH", "mjpeg")),
                 asyncio.create_task(stream("/detections?camera_id=BENCH", "detections")),
                 asyncio.create_task(stream("/alerts", "alerts"))]
        await asyncio.sleep(min(10, seconds / 3))
        tasks.append(asyncio.create_task(controls()))
        await asyncio.sleep(max(0, seconds - min(10, seconds / 3)))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return result


def summarize(traces, client, start, warmup, duration):
    events = [e for trace in traces for e in trace["events"]]
    events.sort(key=lambda e: e["at"])
    cutoff, end = start + warmup, start + duration
    measured = [e for e in events if cutoff <= e["at"] < end]
    stages = sorted({e["stage"] for e in measured})
    timings = {stage: distribution([e["ms"] for e in measured if e["stage"] == stage and e["ms"] is not None]) for stage in stages}

    def fps_bins(times):
        bins = [0] * max(0, int(duration - warmup))
        for stamp in times:
            index = int(stamp - cutoff)
            if cutoff <= stamp < end and 0 <= index < len(bins):
                bins[index] += 1
        return {"one_second_bins": bins, **distribution(bins)}

    count = lambda stage: sum(e["stage"] == stage for e in measured)
    alert_decisions = [e for e in measured if e["stage"] == "alert_decision" and e.get("alert_id")]
    sse_emitted = [e for e in measured if e["stage"] == "sse_emitted" and e.get("alert_id")]
    decisions_by_id = {e["alert_id"]: e for e in alert_decisions}
    sse_by_id = {e["alert_id"]: e for e in sse_emitted}
    matched_alerts = [
        (decisions_by_id[alert_id], sse_by_id[alert_id])
        for alert_id in sorted(decisions_by_id.keys() & sse_by_id.keys())
    ]
    alert_latency_values = [
        {"alert_id": e["alert_id"], "alertLatencyMs": e.get("alertLatencyMs")}
        for e in sse_emitted
    ]
    display = [e["at"] for e in events if e["stage"] == "display"]
    ipc = sum(e.get("bytes", 0) for e in measured if e["stage"] == "ipc_enqueue")
    interval = max(duration - warmup, 1)
    return {"trace_available": bool(events), "stage_latency_ms": timings, "render_fps": fps_bins(display) if any(e['stage'] == 'display' for e in events) else None, "client_fps": fps_bins(client.get("mjpeg_times", [])) if client.get('mjpeg_times') else None,
            "capture_fps": fps_bins([e["at"] for e in measured if e["stage"] == "capture" and e["ok"]]) if any(e["stage"] == "capture" for e in events) else None,
            "model_call_counts": {stage: count(stage) for stage in ("violence_window", "weapon_window", "person_onnx", "person_yolo")},
            "accepted_raw_ipc_bytes_per_second": ipc / interval, "ipc_dropped_frames": count("ipc_drop"),
            "alert_count": count("alert"),
            "alert_latency": {
                "decision_count": len(alert_decisions),
                "sse_emitted_count": len(sse_emitted),
                "matched_alert_count": len(matched_alerts),
                "capture_to_decision_ms": distribution([
                    (decision["at"] - decision["capture_timestamp"]) * 1000
                    for decision in alert_decisions
                    if isinstance(decision.get("capture_timestamp"), (int, float))
                    and decision["capture_timestamp"] <= decision["at"]
                ]),
                "decision_to_sse_emitted_ms": distribution([
                    (sse["at"] - decision["at"]) * 1000
                    for decision, sse in matched_alerts
                ]),
                "capture_to_sse_emitted_ms": distribution([
                    (sse["at"] - decision["capture_timestamp"]) * 1000
                    for decision, sse in matched_alerts
                    if isinstance(decision.get("capture_timestamp"), (int, float))
                ]),
                "alertLatencyMs_values": alert_latency_values,
                "alertLatencyMs": distribution([
                    value["alertLatencyMs"] for value in alert_latency_values
                    if isinstance(value["alertLatencyMs"], (int, float))
                ]),
            },
            "first_display_seconds": min(display) - start if display else None,
            "post_set_threshold_ms": distribution([r["ms"] for r in client.get("requests", []) if r.get("status") == 200 and r.get("route", "/set_threshold") == "/set_threshold"]),
            "control_routes_ms": {route: distribution([r["ms"] for r in client.get("requests", []) if r.get("route") == route and r.get("status") == 200]) for route in sorted({r.get("route", "/set_threshold") for r in client.get("requests", [])})},
            "post_failures": [r for r in client.get("requests", []) if r.get("status") != 200],
            "glass_to_alert_ms": None, "glass_to_display_ms": None,
            "unmeasured_reasons": {"glass_latency": "No independently verified event onset or glass-to-display clock; processing timestamps alone are not glass latency.",
                                   "accuracy": "No verified held-out labels provided for this throughput run.",
                                   "all_mutating_endpoints": "Only the recorded local control workload is exercised; external-effect/source-changing endpoints and live G-15 remain unproven."},
            "models": list({json.dumps(trace["models"], sort_keys=True): trace["models"] for trace in traces if trace["models"]}.values()),
            "complete_gates_passed": []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(ROOT / "demo_assets/videos/Wq0BuA8GM84_0.avi"))
    parser.add_argument("--seconds", type=int, default=75)
    parser.add_argument("--warmup", type=int, default=25)
    parser.add_argument("--output", type=Path, default=ROOT / "bench/results/baseline")
    parser.add_argument("--all-detection", action="store_true")
    parser.add_argument("--chunk-traces", action="store_true", help="Flush trace chunks so long-run instrumentation does not grow worker memory")
    parser.add_argument("--extended-controls", action="store_true", help="Exercise unchanged threshold, cooldown and full-policy controls")
    args = parser.parse_args()
    if not 0 <= args.warmup < args.seconds <= 7200:
        parser.error("Require 0 <= warmup < seconds <= 7200")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    args_list = [sys.executable, "-m", "bench.runtime", "--output", str(output), "--source", args.source,
                 "--port", str(port), "--seconds", str(args.seconds)]
    if args.all_detection:
        args_list.append("--all-detection")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    if args.chunk_traces:
        env["SENTINEL_BENCH_CHUNK_TRACES"] = "1"
    snapshot = environment()
    snapshot["harness_hashes"] = {str(p.relative_to(ROOT)): sha256(p) for p in sorted((ROOT / "bench").glob("*.py"))}
    source = Path(args.source)
    snapshot["source"] = {"path": args.source, "sha256": sha256(source)} if source.is_file() else {"camera_index": args.source}
    snapshot["all_detection_requested"] = args.all_detection
    snapshot["inference_tuning"] = {
        "violence_preprocess_workers": os.environ.get("AI_SENTINEL_VIOLENCE_PREPROCESS_WORKERS", "4"),
        "ort_intra_op_threads": os.environ.get("AI_SENTINEL_ORT_INTRA_OP_THREADS", "2"),
        "violence_cudnn_benchmark": os.environ.get("AI_SENTINEL_VIOLENCE_CUDNN_BENCHMARK", "1"),
        "violence_channels_last_3d": os.environ.get("AI_SENTINEL_VIOLENCE_CHANNELS_LAST_3D", "1"),
        "violence_pinned_host_tensor": os.environ.get("AI_SENTINEL_VIOLENCE_PINNED_HOST_TENSOR", "1"),
        "violence_fp16_autocast": os.environ.get("AI_SENTINEL_VIOLENCE_FP16_AUTOCAST", "1"),
        "violence_warmup_at_load": os.environ.get("AI_SENTINEL_VIOLENCE_WARMUP_AT_LOAD", "1"),
    }
    gpu_samples = []
    cpu_samples = []
    cpu_sample_seconds = 0.0
    logical_processors = os.cpu_count() or 1
    launch_started = time.perf_counter()
    previous_cpu_at = launch_started
    previous_cpu_seconds = 0.0
    try:
        import psutil
        benchmark_process = psutil.Process(os.getpid())
    except (ImportError, OSError):
        benchmark_process = None

    def process_tree_cpu_seconds():
        if benchmark_process is None:
            return None
        try:
            processes = [benchmark_process, *benchmark_process.children(recursive=True)]
            return sum(
                child.cpu_times().user + child.cpu_times().system
                for child in processes
                if child.is_running()
            )
        except (psutil.Error, OSError, AttributeError):
            return None

    previous_cpu_seconds = process_tree_cpu_seconds() or 0.0
    client_result = {}
    measurement_start = None
    startup_deadline = launch_started + args.seconds + 120
    ready_marker = output / "benchmark-start.json"
    with (output / "runtime.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(args_list, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            import httpx
            client_future = None
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as executor:
                while process.poll() is None:
                    now = time.perf_counter()
                    if measurement_start is None and now >= startup_deadline:
                        break
                    if measurement_start is not None and now - measurement_start >= args.seconds + 15:
                        break
                    if client_future is None:
                        try:
                            response = httpx.get(f"http://127.0.0.1:{port}/security/status", timeout=1, trust_env=False)
                            marker = json.loads(ready_marker.read_text(encoding="utf-8")) if ready_marker.exists() else {}
                            if response.status_code == 200 and marker.get("ready"):
                                measurement_start = float(marker["started_monotonic"])
                                client_future = executor.submit(asyncio.run, observe(
                                    f"http://127.0.0.1:{port}",
                                    max(1, args.seconds - 2),
                                    args.extended_controls,
                                ))
                        except httpx.HTTPError:
                            pass
                    try:
                        import psutil
                        memory = psutil.virtual_memory()
                        parent = psutil.Process(process.pid)
                        rss = sum(p.memory_info().rss for p in [parent, *parent.children(recursive=True)])
                        row = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                                             capture_output=True, text=True, timeout=3, check=True).stdout.strip()
                        gpu_samples.append({"at": time.perf_counter(), "gpu_percent,vram_mib": row,
                                            "process_tree_rss_bytes": rss, "system_available_bytes": memory.available})
                    except (psutil.Error, OSError, subprocess.SubprocessError, AttributeError) as exc:
                        gpu_samples.append({"error": type(exc).__name__})
                    cpu_at = time.perf_counter()
                    current_cpu_seconds = process_tree_cpu_seconds()
                    if current_cpu_seconds is not None:
                        interval_seconds = max(cpu_at - previous_cpu_at, 1e-6)
                        if (measurement_start is not None and
                                cpu_at >= measurement_start + args.warmup and
                                previous_cpu_at >= measurement_start + args.warmup):
                            cpu_samples.append(max(0.0, current_cpu_seconds - previous_cpu_seconds) /
                                               interval_seconds / logical_processors * 100)
                            cpu_sample_seconds += interval_seconds
                        previous_cpu_at = cpu_at
                        previous_cpu_seconds = current_cpu_seconds
                    time.sleep(1)
                if client_future is not None:
                    try:
                        client_result = client_future.result(timeout=25)
                    except Exception as exc:
                        client_result = {"error": type(exc).__name__}
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                client_result["shutdown_timeout"] = True
        finally:
            if process.poll() is None:
                # Only the process started by this invocation is terminated.
                import psutil
                children = psutil.Process(process.pid).children(recursive=True)
                process.terminate()
                for child in children:
                    with contextlib.suppress(psutil.NoSuchProcess):
                        child.terminate()
                process.wait(timeout=10)
    traces = [json.loads(p.read_text(encoding="utf-8")) for p in output.glob("trace-*.json")]
    write_json(output / "client.json", client_result)
    benchmark_start = measurement_start if measurement_start is not None else launch_started
    report = {"environment": snapshot, "started_monotonic": benchmark_start,
              "launched_monotonic": launch_started,
              "startup_delay_seconds": round(benchmark_start - launch_started, 3),
              "seconds": args.seconds, "warmup_seconds": args.warmup,
              "runtime_exit_code": process.returncode, "gpu_samples": gpu_samples,
              "summary": summarize(traces, client_result, benchmark_start, args.warmup, args.seconds)}
    summary = report["summary"]
    cpu_summary = {
        "metric": "Python process-tree CPU share of total machine capacity",
        "mean_percent": round(statistics.mean(cpu_samples), 2) if cpu_samples else None,
        "p50_percent": distribution(cpu_samples)["p50"],
        "p95_percent": distribution(cpu_samples)["p95"],
        "sample_count": len(cpu_samples),
        "measured_seconds": round(cpu_sample_seconds, 2),
        "logical_processors": logical_processors,
        "measurement_window": f"Measured portion after the {args.warmup}-second warmup",
        "method": "Python benchmark runner and recursive child process CPU-time deltas normalized by elapsed time and logical processor count.",
        "workload_valid": cpu_sample_seconds >= max(0.0, args.seconds - args.warmup - 5),
        "runtime_exit_code": process.returncode,
    }
    write_json(output / "cpu-summary.json", cpu_summary)
    active = bool(summary["render_fps"] and (summary["render_fps"]["p50"] or 0) > 0)
    counts = summary["model_call_counts"]
    if args.all_detection:
        active = active and all(counts[name] > 0 for name in ("violence_window", "weapon_window", "person_onnx"))
    ready = bool(measurement_start is not None)
    report["models_ready"] = ready
    report["workload_valid"] = bool(ready and active and process.returncode == 0 and not client_result.get("shutdown_timeout"))
    write_json(output / "report.json", report)
    print(json.dumps(report["summary"], indent=2))
    return 0 if report["workload_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
