import os
import json
import argparse
from pathlib import Path

def build_manifest(dataset_dir: str, output_path: str):
    dataset_path = Path(dataset_dir)
    manifest = []
    
    # RWF-2000 typically has:
    # dataset/train/Fight
    # dataset/train/NonFight
    # dataset/val/Fight
    # dataset/val/NonFight
    
    for split in ["train", "val"]:
        split_path = dataset_path / split
        if not split_path.exists():
            print(f"Split path {split_path} not found, skipping.")
            continue
            
        for original_label in ["Fight", "NonFight", "fight", "nonfight", "Violence", "Normal", "violence", "normal"]:
            label_path = split_path / original_label
            if not label_path.exists():
                continue
                
            # Map labels
            unified_label = "violence" if original_label.lower() == "fight" else "normal"
            
            # Support both .mp4 and .avi
            for ext in ["*.mp4", "*.avi"]:
                for video_file in label_path.glob(ext):
                    # Avoid double-counting on case-insensitive filesystems (Windows)
                    # by checking if we've already processed this file.
                    # We use the absolute path as the unique key.
                    abs_path = str(video_file.absolute())
                    if any(e["video_path"].lower() == abs_path.lower() for e in manifest):
                        continue

                    entry = {
                        "video_path": abs_path,
                        "label": unified_label,
                        "source_dataset": "rwf2000_kaggle",
                        "split": split,
                        "camera_angle": "cctv_like",
                        "license_note": "RWF-2000 usage restrictions apply; do not redistribute videos.",
                        "original_label": original_label
                    }
                    manifest.append(entry)
                
    print(f"Found {len(manifest)} videos.")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in manifest:
            f.write(json.dumps(entry) + "\n")
            
    print(f"Manifest written to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build RWF-2000 Manifest")
    parser.add_argument("--dir", required=True, help="RWF-2000 root directory")
    parser.add_argument("--output", required=True, help="Output manifest path (.jsonl)")
    
    args = parser.parse_args()
    build_manifest(args.dir, args.output)
