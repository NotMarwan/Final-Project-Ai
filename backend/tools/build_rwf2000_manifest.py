import os
import json
import argparse
import random
from pathlib import Path

def build_manifest(dataset_dir: str, output_path: str, val_ratio: float = None, seed: int = 42):
    dataset_path = Path(dataset_dir)
    manifest = []
    
    # RWF-2000 typically has:
    # dataset/train/Fight
    # dataset/train/NonFight
    # dataset/val/Fight
    # dataset/val/NonFight
    
    # Search for all avi/mp4 files in the directory
    # We first collect them to allow for re-splitting if requested
    
    # Standard splits in folder structure
    potential_splits = ["train", "val", "test"]
    
    for split in potential_splits:
        split_path = dataset_path / split
        if not split_path.exists():
            continue
        
        # Iterate over all label directories in the current split folder
        for label_dir in split_path.iterdir():
            if not label_dir.is_dir():
                continue  # Skip files, only process directories
            original_label = label_dir.name
            label_lower = original_label.lower()
            
            # Define exact matches for violence and normal labels (lowercase)
            violence_exact = {"fight", "violence", "violent"}
            normal_exact = {
                "nonfight", "non-fight", "non_fight",
                "normal",
                "nonviolence", "non-violence", "non_violence"
            }
            
            # Determine unified label
            if label_lower in violence_exact:
                unified_label = "violence"
            elif label_lower in normal_exact:
                unified_label = "normal"
            else:
                print(f"Warning: Unrecognized label '{original_label}' in {split_path}, skipping.")
                continue
            
            label_path = label_dir  # The label directory is the current label_dir
            
            # Support both .mp4 and .avi
            for ext in ["*.mp4", "*.avi"]:
                for video_file in label_path.glob(ext):
                    abs_path = str(video_file.absolute())
                    # Check for duplicates (case-insensitive)
                    if any(e["video_path"].lower() == abs_path.lower() for e in manifest):
                        continue
                    
                    entry = {
                        "video_path": abs_path,
                        "label": unified_label,
                        "source_dataset": "rwf2000_kaggle",
                        "split": split,  # Default from folder structure
                        "original_split": split,
                        "camera_angle": "cctv_like",
                        "license_note": "RWF-2000 usage restrictions apply; do not redistribute videos.",
                        "original_label": original_label
                    }
                    manifest.append(entry)
                
    print(f"Found {len(manifest)} videos.")
    
    # Apply re-splitting if requested
    if val_ratio is not None:
        print(f"Re-splitting manifest with val_ratio={val_ratio} and seed={seed}")
        random.seed(seed)
        random.shuffle(manifest)
        
        val_count = int(len(manifest) * val_ratio)
        # Ensure at least 1 val if we have samples and ratio > 0
        if val_count == 0 and len(manifest) > 0 and val_ratio > 0:
            val_count = 1
            
        for i, entry in enumerate(manifest):
            if i < val_count:
                entry["split"] = "val"
            else:
                entry["split"] = "train"
        
        # Sort back for deterministic output order (by path)
        manifest.sort(key=lambda x: x["video_path"])

    # Report distribution
    dist = {}
    for e in manifest:
        k = (e["split"], e["label"])
        dist[k] = dist.get(k, 0) + 1
    
    print("Distribution:")
    for (split, label), count in sorted(dist.items()):
        print(f"  {split} / {label}: {count}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in manifest:
            f.write(json.dumps(entry) + "\n")
            
    print(f"Manifest written to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build RWF-2000 Manifest")
    parser.add_argument("--dir", required=True, help="RWF-2000 root directory")
    parser.add_argument("--output", required=True, help="Output manifest path (.jsonl)")
    parser.add_argument("--val-ratio", type=float, default=None, help="Optional override for validation split ratio (0.0 to 1.0)")
    parser.add_argument("--seed", type=int, default=42, help="Seed for reproducible re-splitting")
    
    args = parser.parse_args()
    build_manifest(args.dir, args.output, args.val_ratio, args.seed)
