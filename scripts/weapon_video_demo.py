"""
weapon_video_demo.py
====================
Run weapon detection on project sample videos and produce output videos
with styled bounding boxes overlaid in real-time.

Usage:
    python scripts/weapon_video_demo.py --input backend/cam1.avi --output public/weapon-detections/cam1_weapon_demo.avi
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

# ── Color Theme ──
COLOR_MAP = {
    "pistol": (0, 140, 255),    # Orange-Red
    "knife":  (0, 255, 127),    # Spring Green
    "default": (255, 200, 0),   # Yellow
}
HEADER_BG = (15, 15, 35)
HEADER_TEXT = (0, 200, 255)
SAFE_GREEN = (100, 255, 100)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Weapon detection on video with styled overlay")
    parser.add_argument("--input", default="backend/cam1.avi", help="Input video path")
    parser.add_argument("--output", default="public/weapon-detections/cam1_weapon_demo.avi", help="Output video path")
    parser.add_argument("--weights", default="backend/weapon_yolo.pt", help="YOLO weights path")
    parser.add_argument("--conf", type=float, default=0.20, help="Confidence threshold")
    parser.add_argument("--max-frames", type=int, default=0, help="Max frames to process (0 = all)")
    parser.add_argument("--fps", type=float, default=30.0, help="Output FPS")
    parser.add_argument("--quality", choices=["low", "medium", "high"], default="high", help="JPEG quality")
    parser.add_argument("--fast", action="store_true", help="Fast annotation mode (no trails/glow)")
    parser.add_argument("--device", default=None, help="Inference device (cuda, cpu). Auto-detect if not set.")
    return parser.parse_args()


def draw_header(canvas: np.ndarray, frame_num: int, total_frames: int, latency_ms: float, detections: int) -> None:
    """Draw top header bar with live stats."""
    h, w = canvas.shape[:2]
    # Header background
    cv2.rectangle(canvas, (0, 0), (w, 60), HEADER_BG, -1)
    
    # Title
    cv2.putText(canvas, "AI SENTINEL  WEAPON DETECTION", (20, 25), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, HEADER_TEXT, 2)
    
    # Stats line
    progress = f"Frame: {frame_num}/{total_frames}" if total_frames > 0 else f"Frame: {frame_num}"
    status_text = f"{progress}  |  Latency: {latency_ms:.1f}ms  |  Detections: {detections}"
    cv2.putText(canvas, status_text, (20, 50), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)
    
    # Live indicator dot
    blink = int(time.time() * 2) % 2
    dot_color = (0, 255, 0) if blink else (0, 150, 0)
    cv2.circle(canvas, (w - 30, 20), 6, dot_color, -1)
    cv2.putText(canvas, "LIVE", (w - 80, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, dot_color, 1)


def draw_detections(frame: np.ndarray, results, model_names: dict) -> tuple[np.ndarray, int]:
    """Draw styled bounding boxes on frame. Returns (annotated_frame, detection_count)."""
    detections = 0
    
    if results[0].boxes is None:
        # No detections - show SAFE status
        h, w = frame.shape[:2]
        cv2.putText(frame, "SAFE  NO WEAPON", (w//2 - 100, h//2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, SAFE_GREEN, 2)
        return frame, 0
    
    for box in results[0].boxes:
        cls_id = int(box.cls[0].item())
        conf = float(box.conf[0].item())
        label = model_names.get(cls_id, f"class_{cls_id}")
        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
        
        color = COLOR_MAP.get(label, COLOR_MAP["default"])
        
        # Outer glow
        cv2.rectangle(frame, (x1-2, y1-2), (x2+2, y2+2), color, 3)
        # Inner box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        
        # Label background
        label_text = f"{label.upper()} {conf*100:.0f}%"
        (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 8, y1), color, -1)
        cv2.putText(frame, label_text, (x1 + 4, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
        
        # Corner brackets
        bl = 12
        cv2.line(frame, (x1, y1), (x1 + bl, y1), (255, 255, 255), 2)
        cv2.line(frame, (x1, y1), (x1, y1 + bl), (255, 255, 255), 2)
        cv2.line(frame, (x2, y1), (x2 - bl, y1), (255, 255, 255), 2)
        cv2.line(frame, (x2, y1), (x2, y1 + bl), (255, 255, 255), 2)
        cv2.line(frame, (x1, y2), (x1 + bl, y2), (255, 255, 255), 2)
        cv2.line(frame, (x1, y2), (x1, y2 - bl), (255, 255, 255), 2)
        cv2.line(frame, (x2, y2), (x2 - bl, y2), (255, 255, 255), 2)
        cv2.line(frame, (x2, y2), (x2, y2 - bl), (255, 255, 255), 2)
        
        detections += 1
    
    return frame, detections


def main() -> int:
    args = parse_args()
    
    print("=" * 60)
    print(" AI SENTINEL  Video Weapon Detection Demo")
    print("=" * 60)
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print(f"Weights: {args.weights}")
    print()
    
    # Load model
    print("Loading YOLO model...")
    if not os.path.exists(args.weights):
        print(f"ERROR: Weights not found: {args.weights}")
        return 1
    
    if args.device:
        model_device = args.device
    else:
        try:
            from backend.device_config import get_optimal_device
            model_device = str(get_optimal_device())
        except ImportError:
            model_device = "cpu"
    model = YOLO(args.weights)
    model_names = {int(k): str(v).lower() for k, v in model.names.items()}
    print(f"Model loaded (device={model_device}). Classes: {list(model_names.values())}")
    print()
    
    # Open video
    cap = cv2.VideoCapture(args.input)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video: {args.input}")
        return 1
    
    in_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    in_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    in_fps = cap.get(cv2.CAP_PROP_FPS) or args.fps
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    
    print(f"Video: {in_w}x{in_h} @ {in_fps:.1f}fps, {total} frames")
    
    # Setup writer (add 60px header)
    out_h = in_h + 60
    fourcc = cv2.VideoWriter_fourcc(*"XVID")
    writer = cv2.VideoWriter(args.output, fourcc, args.fps, (in_w, out_h))
    
    if not writer.isOpened():
        print("WARNING: XVID failed, trying MJPG...")
        writer = cv2.VideoWriter(args.output, cv2.VideoWriter_fourcc(*"MJPG"), args.fps, (in_w, out_h))
    
    frame_num = 0
    total_detections = 0
    max_conf = 0.0
    start_time = time.time()
    
    print("\nProcessing frames...")
    print("-" * 60)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_num += 1
        
        # Run detection
        infer_start = time.perf_counter()
        results = model(frame, verbose=False, conf=args.conf, device=model_device)
        latency_ms = (time.perf_counter() - infer_start) * 1000
        
        # Draw detections
        annotated, dets = draw_detections(frame.copy(), results, model_names)
        total_detections += dets
        
        # Track max confidence
        if results[0].boxes is not None:
            for box in results[0].boxes:
                conf = float(box.conf[0].item())
                max_conf = max(max_conf, conf)
        
        # Add header
        canvas = np.zeros((out_h, in_w, 3), dtype=np.uint8)
        canvas[60:, :] = annotated
        draw_header(canvas, frame_num, total, latency_ms, dets)
        
        # Write frame
        writer.write(canvas)
        
        # Progress
        if frame_num % 30 == 0 or dets > 0:
            status = f"WEAPON! ({dets})" if dets > 0 else "SAFE"
            print(f"  Frame {frame_num:4d}: {status:15s} | Latency: {latency_ms:6.1f}ms | MaxConf: {max_conf:.2f}")
        
        if args.max_frames > 0 and frame_num >= args.max_frames:
            break
    
    cap.release()
    writer.release()
    
    elapsed = time.time() - start_time
    
    print("-" * 60)
    print(f"\nDone!")
    print(f"  Frames processed: {frame_num}")
    print(f"  Total detections: {total_detections}")
    print(f"  Max confidence:   {max_conf*100:.1f}%")
    print(f"  Avg FPS:          {frame_num/elapsed:.1f}")
    print(f"  Output:           {args.output}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
