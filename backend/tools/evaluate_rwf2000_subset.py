import os
import json
import time
import torch
import cv2
import numpy as np
import argparse
from pathlib import Path
from typing import List, Dict

# Add backend to path
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from inference import X3DViolenceModel, preprocess_window

def evaluate_subset(manifest_path: str, weights_path: str, samples_per_class: int = 10):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # Load model
    model = X3DViolenceModel(num_classes=2).to(device)
    if os.path.exists(weights_path):
        try:
            model.load_state_dict(torch.load(weights_path, map_location=device))
            print(f"Loaded weights from {weights_path}")
        except Exception as e:
            print(f"Warning: Could not load weights: {e}. Using random initialization.")
    else:
        print(f"Weights file {weights_path} not found. Using random initialization for baseline.")
    
    model.eval()
    
    # Load manifest
    entries = []
    with open(manifest_path, "r") as f:
        for line in f:
            entries.append(json.loads(line))
            
    # Sample subsets
    violence_samples = [e for e in entries if e["label"] == "violence"]
    normal_samples = [e for e in entries if e["label"] == "normal"]
    
    # Use val split if possible, otherwise just sample
    val_violence = [e for e in violence_samples if e["split"] == "val"]
    val_normal = [e for e in normal_samples if e["split"] == "val"]
    
    if not val_violence: val_violence = violence_samples
    if not val_normal: val_normal = normal_samples
    
    subset = val_violence[:samples_per_class] + val_normal[:samples_per_class]
    print(f"Evaluating {len(subset)} samples ({len(val_violence[:samples_per_class])} violence, {len(val_normal[:samples_per_class])} normal).")
    
    results = []
    latencies = []
    
    for entry in subset:
        video_path = entry["video_path"]
        target = 1 if entry["label"] == "violence" else 0
        
        cap = cv2.VideoCapture(video_path)
        frames = []
        while len(frames) < 32:
            ret, frame = cap.read()
            if not ret: break
            frames.append(frame)
        cap.release()
        
        if len(frames) < 32:
            print(f"Skipping {video_path}: insufficient frames ({len(frames)})")
            continue
            
        # Preprocess
        input_tensor = preprocess_window(frames).to(device)
        
        # Infer
        start_time = time.perf_counter()
        with torch.no_grad():
            output = model(input_tensor)
            prob = torch.softmax(output, dim=1)[0][1].item()
        latency = (time.perf_counter() - start_time) * 1000
        latencies.append(latency)
        
        pred = 1 if prob > 0.5 else 0
        results.append({
            "path": video_path,
            "target": target,
            "pred": pred,
            "prob": prob,
            "latency": latency
        })
        
        status = "CORRECT" if pred == target else "WRONG"
        print(f"[{status}] {Path(video_path).name}: target={target}, pred={pred}, prob={prob:.4f}, latency={latency:.2f}ms")
        
    # Stats
    correct = sum(1 for r in results if r["pred"] == r["target"])
    tp = sum(1 for r in results if r["pred"] == 1 and r["target"] == 1)
    fp = sum(1 for r in results if r["pred"] == 1 and r["target"] == 0)
    fn = sum(1 for r in results if r["pred"] == 0 and r["target"] == 1)
    tn = sum(1 for r in results if r["pred"] == 0 and r["target"] == 0)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    accuracy = correct / len(results) if len(results) > 0 else 0
    
    print("\n" + "="*30)
    print("BASELINE EVALUATION RESULTS")
    print("="*30)
    print(f"Total Evaluated: {len(results)}")
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"Avg Latency: {np.mean(latencies):.2f}ms")
    print(f"P95 Latency: {np.percentile(latencies, 95):.2f}ms")
    print("="*30)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate RWF-2000 Subset")
    parser.add_argument("--manifest", required=True, help="Path to manifest.jsonl")
    parser.add_argument("--weights", default="backend/best_model.pt", help="Path to weights")
    parser.add_argument("--samples", type=int, default=10, help="Samples per class")
    
    args = parser.parse_args()
    evaluate_subset(args.manifest, args.weights, args.samples)
