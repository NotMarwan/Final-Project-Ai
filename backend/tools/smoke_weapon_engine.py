import os
import sys
import time
import argparse
import json
import numpy as np
import threading
from statistics import median, mean

# Add backend to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from weapon import WeaponSignalEngine, WeaponConfig
except ImportError as e:
    print(json.dumps({"error": f"Import failed: {str(e)}", "success": False}))
    sys.exit(1)

def run_smoke_test(timeout_sec=30, runs=5, warmup=1):
    results = {
        "engine_imported": True,
        "success": True,
        "ready_before": False,
        "ready_after": False,
        "status_reason": "",
        "device": "unknown",
        "load_latency_ms": 0.0,
        "first_inference_latency_ms": 0.0,
        "warm_latencies": [],
        "warm_p50": 0.0,
        "warm_p95": 0.0,
        "max_warm": 0.0,
        "runs_attempted": 0,
        "runs_completed": 0,
        "labels": [],
        "weights_download_likely_needed": False
    }

    # 1. Initialize engine
    config = WeaponConfig(enabled=True, backend="torchvision_coco", interval=1)
    engine = WeaponSignalEngine(config)
    
    results["ready_before"] = engine.latest_signal().get("ready", False)
    results["device"] = str(engine.device)
    
    # Check if torchvision is installed
    try:
        import torchvision
        results["torchvision_version"] = torchvision.__version__
    except ImportError:
        results["success"] = False
        results["status_reason"] = "torchvision-missing"
        print(json.dumps(results))
        return

    # 2. Prepare synthetic frame
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    frame[200:400, 200:400] = 255

    latencies = []
    
    # 3. Run loop
    total_runs = warmup + runs
    for i in range(total_runs):
        results["runs_attempted"] += 1
        engine.process_frame(frame)
        
        # Wait for this specific inference
        start_wait = time.time()
        while time.time() - start_wait < timeout_sec:
            with engine._lock:
                running = engine._inference_running
                ready = engine._model is not None
            
            if ready and not running:
                break
                
            signal = engine.latest_signal()
            if signal.get("failed"):
                break
            time.sleep(0.1)
        
        signal = engine.latest_signal()
        if signal.get("failed"):
            results["success"] = False
            results["status_reason"] = signal.get("reason", "failed")
            break
            
        if not signal.get("ready"):
            results["success"] = False
            results["status_reason"] = "timeout-or-stuck"
            break

        inf_lat = signal.get("inferenceLatencyMs", 0.0)
        
        if i == 0:
            results["load_latency_ms"] = signal.get("loadLatencyMs", 0.0)
            results["first_inference_latency_ms"] = inf_lat
        elif i >= warmup:
            latencies.append(inf_lat)
            results["runs_completed"] += 1

    # 4. Aggregate results
    final_signal = engine.status()
    results["ready_after"] = final_signal.get("ready", False)
    results["labels"] = final_signal.get("labels", [])
    results["is_realtime"] = final_signal.get("isRealtime", False)
    results["skipped_frames"] = final_signal.get("skippedFrames", 0)
    results["min_interval_ms"] = final_signal.get("minIntervalMs", 2500)
    results["inference_running"] = final_signal.get("inferenceRunning", False)
    
    if latencies:
        latencies.sort()
        results["warm_latencies"] = latencies
        results["warm_p50"] = round(median(latencies), 2)
        # Simple p95 for small sample sizes
        idx = max(0, int(len(latencies) * 0.95) - 1)
        results["warm_p95"] = round(latencies[idx], 2)
        results["max_warm"] = round(max(latencies), 2)
        
    # Recommendation
    results["recommendation"] = {
        "realtime_ready": results["warm_p95"] < 500 and results["device"] != "cpu",
        "recommended_min_interval_ms": int(results["warm_p95"] * 1.2) if latencies else 2500
    }

    if "model-load-failed" in results["status_reason"]:
        results["weights_download_likely_needed"] = True

    # Use stderr for logs, stdout for JSON only
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weapon Engine Warmup Smoke Test")
    parser.add_argument("--timeout-sec", type=int, default=30, help="Seconds to wait per inference")
    parser.add_argument("--runs", type=int, default=5, help="Number of warm runs")
    parser.add_argument("--warmup", type=int, default=1, help="Number of warmup runs")
    args = parser.parse_args()
    
    run_smoke_test(timeout_sec=args.timeout_sec, runs=args.runs, warmup=args.warmup)
