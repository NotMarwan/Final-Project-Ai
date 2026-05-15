"""
weapon_visual_demo.py
======================
Download sample weapon images, run detection, draw styled bounding boxes,
and save entertaining visual results.

Usage:
    python scripts/weapon_visual_demo.py
"""
import os
import sys
import urllib.request
import cv2
import numpy as np
import torch

# Add backend to path
sys.path.insert(0, os.path.abspath("backend"))

from weapon import WeaponConfig, WeaponSignalEngine

# ── Sample Images (Public Domain / Creative Commons) ──
SAMPLE_IMAGES = [
    {
        "name": "sample_pistol_01",
        "url": "https://images.pexels.com/photos/889709/pexels-photo-889709.jpeg?auto=compress&cs=tinysrgb&w=640",
        "desc": "Tactical firearms"
    },
    {
        "name": "sample_knife_01", 
        "url": "https://images.pexels.com/photos/4226910/pexels-photo-4226910.jpeg?auto=compress&cs=tinysrgb&w=640",
        "desc": "Knife on table"
    },
    {
        "name": "sample_mixed_01",
        "url": "https://images.unsplash.com/photo-1595590424283-b8f17842773f?w=640",
        "desc": "Handgun with ammo"
    },
    {
        "name": "sample_knife_02",
        "url": "https://images.pexels.com/photos/9837834/pexels-photo-9837834.jpeg?auto=compress&cs=tinysrgb&w=640",
        "desc": "Blade close-up"
    },
    {
        "name": "sample_pistol_03",
        "url": "https://images.pexels.com/photos/163480/war-desert-guns-gunshow-163480.jpeg?auto=compress&cs=tinysrgb&w=640",
        "desc": "Pistol display"
    },
]

OUTPUT_DIR = "public/weapon-detections"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Color Theme ──
COLOR_MAP = {
    "pistol": (0, 140, 255),    # Orange-Red
    "knife":  (0, 255, 127),    # Spring Green
    "rifle":  (255, 50, 50),    # Red
    "default": (255, 200, 0),   # Yellow
}

BG_COLOR = (15, 15, 35)         # Dark navy background
HEADER_COLOR = (0, 200, 255)    # Cyan header


def download_image(url: str, save_path: str) -> bool:
    """Download image from URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()
            with open(save_path, "wb") as f:
                f.write(data)
        return True
    except Exception as e:
        print(f"  Failed to download: {e}")
        return False


def draw_styled_detection(frame: np.ndarray, detections: list, latency_ms: float) -> np.ndarray:
    """Draw entertaining styled bounding boxes."""
    h, w = frame.shape[:2]
    
    # Create canvas with dark header bar
    canvas = np.zeros((h + 80, w, 3), dtype=np.uint8)
    canvas[:] = BG_COLOR
    canvas[80:, :] = frame
    
    # Header text
    header_text = "AI SENTINEL WEAPON DETECTION"
    cv2.putText(canvas, header_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, HEADER_COLOR, 2)
    
    status_text = f"Status: LIVE | Latency: {latency_ms:.1f}ms"
    cv2.putText(canvas, status_text, (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    
    # Draw detections on frame area
    for conf, label, bbox in detections:
        color = COLOR_MAP.get(label, COLOR_MAP["default"])
        x1, y1, x2, y2 = [int(v) for v in bbox]
        y1 += 80
        y2 += 80
        
        # Glowing box effect (outer)
        cv2.rectangle(canvas, (x1-2, y1-2), (x2+2, y2+2), color, 3)
        # Inner solid box
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        
        # Label background
        label_text = f"{label.upper()} {conf*100:.0f}%"
        (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(canvas, (x1, y1 - th - 10), (x1 + tw + 10, y1), color, -1)
        cv2.putText(canvas, label_text, (x1 + 5, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        
        # Corner brackets
        bracket_len = 15
        cv2.line(canvas, (x1, y1), (x1 + bracket_len, y1), (255, 255, 255), 2)
        cv2.line(canvas, (x1, y1), (x1, y1 + bracket_len), (255, 255, 255), 2)
        cv2.line(canvas, (x2, y1), (x2 - bracket_len, y1), (255, 255, 255), 2)
        cv2.line(canvas, (x2, y1), (x2, y1 + bracket_len), (255, 255, 255), 2)
        cv2.line(canvas, (x1, y2), (x1 + bracket_len, y2), (255, 255, 255), 2)
        cv2.line(canvas, (x1, y2), (x1, y2 - bracket_len), (255, 255, 255), 2)
        cv2.line(canvas, (x2, y2), (x2 - bracket_len, y2), (255, 255, 255), 2)
        cv2.line(canvas, (x2, y2), (x2, y2 - bracket_len), (255, 255, 255), 2)
    
    if not detections:
        cv2.putText(canvas, "NO WEAPON DETECTED", (w//2 - 120, h//2 + 80), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 255, 100), 2)
    
    return canvas


def main():
    print("=" * 60)
    print(" AI SENTINEL — Weapon Detection Visual Demo")
    print("=" * 60)
    
    # Setup engine
    os.environ["WEAPON_BACKEND"] = "yolo"
    os.environ["WEAPON_WEIGHT_PATH"] = "backend/weapon_yolo.pt"
    os.environ["WEAPON_LABELS"] = "pistol,knife"
    
    config = WeaponConfig(
        backend="yolo",
        weight_path="backend/weapon_yolo.pt",
        labels=("pistol", "knife"),
        interval=1,
        min_interval_ms=0,
        min_confidence=0.15,
    )
    try:
        from backend.device_config import get_optimal_device
        demo_device = get_optimal_device()
    except ImportError:
        demo_device = torch.device("cpu")
    engine = WeaponSignalEngine(config, device=demo_device)
    
    print("\nLoading model...")
    if not engine.preload():
        print(f"FAILED: {engine.status()['reason']}")
        return 1
    print("Model loaded.\n")
    
    # Download and process each sample
    for sample in SAMPLE_IMAGES:
        print(f"Processing: {sample['name']} — {sample['desc']}")
        
        img_path = f"{OUTPUT_DIR}/{sample['name']}_original.jpg"
        if not download_image(sample["url"], img_path):
            continue
        
        # Load image
        frame = cv2.imread(img_path)
        if frame is None:
            print("  Could not read image")
            continue
        
        # Run detection via engine
        engine.process_frame(frame)
        import time
        time.sleep(1.5)
        
        # Get raw detections directly from backend
        from ultralytics import YOLO
        model = YOLO("backend/weapon_yolo.pt")
        results = model(frame, verbose=False, conf=0.15)
        result = results[0]
        
        detections = []
        latency = engine.latest_signal()["inferenceLatencyMs"]
        
        if result.boxes is not None:
            for box in result.boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                label = model.names.get(cls_id, f"class_{cls_id}")
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                detections.append((conf, label, (x1, y1, x2, y2)))
        
        # Draw styled result
        annotated = draw_styled_detection(frame, detections, latency)
        
        # Save result
        out_path = f"{OUTPUT_DIR}/{sample['name']}_detected.jpg"
        cv2.imwrite(out_path, annotated)
        
        print(f"  Detections: {len(detections)}")
        for conf, label, _ in detections:
            print(f"    - {label}: {conf*100:.1f}%")
        print(f"  Saved: {out_path}\n")
    
    print("=" * 60)
    print(" Done! Check public/weapon-detections/ for results")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
