import os
import sys
import time
import argparse
import json
import numpy as np
import threading

# Add backend to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from weapon import WeaponSignalEngine, WeaponConfig
except ImportError as e:
    print(json.dumps({"error": f"Import failed: {str(e)}", "success": False}))
    sys.exit(1)

def run_smoke_test(timeout_sec=20):
    results = {
        "engine_imported": True,
        "success": True,
        "ready_before": False,
        "ready_after": False,
        "model_loaded_successfully": False,
        "attempted_inference": False,
        "status_reason": "",
        "device": "unknown",
        "score": 0.0,
        "labels": [],
        "latency_ms": 0.0,
        "weights_download_likely_needed": False
    }

    # 1. Initialize engine
    # Use default torchvision_coco backend
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

    # 2. Prepare synthetic frame (640x640 blank)
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    # Add a high-contrast white rectangle
    frame[200:400, 200:400] = 255

    # 3. Call process_frame (triggers async inference)
    # Since interval is 1, it should trigger immediately
    engine.process_frame(frame)
    results["attempted_inference"] = True
    
    # 4. Wait for async inference to complete or timeout
    start_time = time.time()
    inference_completed = False
    
    while time.time() - start_time < timeout_sec:
        signal = engine.latest_signal()
        if signal.get("ready"):
            results["model_loaded_successfully"] = True
            
        # Check if inference finished (inference_running flips to True then False)
        # engine._inference_running is internal, so we check if latency or score changed from 0
        # or if model is loaded and inference_running is False
        with engine._lock:
            running = engine._inference_running
            ready = engine._model is not None
        
        if ready and not running:
            inference_completed = True
            break
        
        # Check if it failed during load
        if signal.get("reason") and "failed" in signal.get("reason").lower():
            break
            
        time.sleep(0.5)

    # 5. Final report
    final_signal = engine.status()
    results["ready_after"] = final_signal.get("ready", False)
    results["score"] = final_signal.get("score", 0.0)
    results["labels"] = final_signal.get("labels", [])
    results["latency_ms"] = final_signal.get("latencyMs", 0.0)
    results["status_reason"] = final_signal.get("reason", "")
    
    if "model-load-failed" in results["status_reason"]:
        results["success"] = False
        # Heuristic: if it failed quickly with a load error, weights might be missing/offline
        results["weights_download_likely_needed"] = True

    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weapon Engine Runtime Smoke Test")
    parser.add_argument("--timeout-sec", type=int, default=20, help="Seconds to wait for model load and inference")
    args = parser.parse_args()
    
    run_smoke_test(timeout_sec=args.timeout_sec)
