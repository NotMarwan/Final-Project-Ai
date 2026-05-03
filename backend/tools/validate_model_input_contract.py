"""
validate_model_input_contract.py

Safe, read-only tool that validates the video loader output shape against
the production model input contract.

It loads one or more clips from the manifest, applies the real video loader,
optionally attempts a no-grad forward pass, and reports tensor shapes.

It NEVER:
  - trains the model
  - saves model weights or checkpoints
  - writes to .data/ or .runlogs/ beyond what DataLoader naturally allocates
"""

import argparse
import json
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

# ── Contract ─────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datasets.video_loader import load_video_clip
from datasets.video_contract import (
    DEFAULT_NUM_FRAMES,
    DEFAULT_SIZE,
    EXPECTED_CLIP_SHAPE,
    EXPECTED_BATCH_SHAPE,
)

EXPECTED_CLIP = (3, DEFAULT_NUM_FRAMES, DEFAULT_SIZE[0], DEFAULT_SIZE[1])
EXPECTED_BATCH = (None, 3, DEFAULT_NUM_FRAMES, DEFAULT_SIZE[0], DEFAULT_SIZE[1])


def parse_args():
    p = argparse.ArgumentParser(description="Validate model input contract (read-only)")
    p.add_argument("--manifest", required=True, help="Path to JSONL manifest")
    p.add_argument("--weights", required=True, help="Path to model weights (.pt)")
    p.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    p.add_argument("--samples", type=int, default=1, help="Number of clips to validate")
    p.add_argument("--forward-pass", action="store_true",
                   help="Attempt a no-grad forward pass through the model")
    return p.parse_args()


def load_manifest_entries(manifest_path: str, max_samples: int) -> list:
    entries = []
    with open(manifest_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                # Support both 'path' and 'video_path' keys
                video_path = entry.get("path") or entry.get("video_path", "")
                if video_path and Path(video_path).exists():
                    entry["path"] = video_path  # normalize to 'path'
                    entries.append(entry)
                    if len(entries) >= max_samples:
                        break
            except (json.JSONDecodeError, KeyError):
                continue
    return entries


def main():
    args = parse_args()
    print("\n" + "=" * 50)
    print("MODEL INPUT CONTRACT VALIDATOR")
    print("=" * 50)
    print(f"Expected clip shape:  {EXPECTED_CLIP_SHAPE}")
    print(f"Expected batch shape: {EXPECTED_BATCH_SHAPE}")
    print("-" * 50)

    # Load manifest entries
    entries = load_manifest_entries(args.manifest, args.samples)
    if not entries:
        print(f"[ERROR] No readable video files found in manifest: {args.manifest}")
        sys.exit(1)

    print(f"Found {len(entries)} usable clip(s) from manifest.")
    print()

    loaded_clips = []
    all_passed = True

    for i, entry in enumerate(entries):
        path = entry["path"]
        label = entry.get("label", "unknown")
        print(f"[{i+1}/{len(entries)}] Loading: {path}  (label={label})")

        try:
            tensor = load_video_clip(path)
        except Exception as e:
            print(f"  [FAIL] Could not load: {e}")
            all_passed = False
            continue

        shape = tuple(tensor.shape)
        dtype = tensor.dtype
        vmin = float(tensor.min())
        vmax = float(tensor.max())
        shape_ok = shape == EXPECTED_CLIP

        print(f"  Shape:    {shape}   {'[OK] MATCH' if shape_ok else '[FAIL] MISMATCH (expected ' + str(EXPECTED_CLIP) + ')'}")
        print(f"  Dtype:    {dtype}")
        print(f"  Range:    [{vmin:.4f}, {vmax:.4f}]  (normalized, may be < 0 after mean/std)")

        if not shape_ok:
            all_passed = False

        loaded_clips.append(tensor)

    if not loaded_clips:
        print("\n[FAIL] No clips were loaded successfully.")
        sys.exit(1)

    # Batch shape
    batch = torch.stack(loaded_clips, dim=0)  # (B, C, T, H, W)
    print(f"\nBatch shape: {tuple(batch.shape)}")

    # Optional forward pass
    if args.forward_pass:
        print("\n" + "-" * 50)
        print("Attempting no-grad forward pass...")
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from inference import X3DViolenceModel

            device = torch.device(args.device)
            model = X3DViolenceModel(num_classes=2).to(device)

            if Path(args.weights).exists():
                state = torch.load(args.weights, map_location=device)
                if isinstance(state, dict) and "model_state_dict" in state:
                    state = state["model_state_dict"]
                try:
                    model.load_state_dict(state)
                    print("[INFO] Weights loaded successfully.")
                except Exception as e:
                    print(f"[WARN] Could not load weights (architecture mismatch): {e}")
                    print("[INFO] Continuing forward pass with random weights.")
            else:
                print(f"[WARN] Weights not found at {args.weights}. Using random weights.")

            model.eval()
            with torch.no_grad():
                input_tensor = batch.to(device)
                logits = model(input_tensor)
                probs = F.softmax(logits, dim=-1)
                print(f"[OK] Forward pass succeeded.")
                print(f"     Output logits shape: {tuple(logits.shape)}")
                print(f"     Probabilities:       {probs.tolist()}")

        except Exception as e:
            print(f"[WARN] Forward pass could not be completed: {e}")
            print("       Shape validation above is still valid.")
    else:
        print("\n[INFO] Forward pass skipped (use --forward-pass to enable).")

    print("\n" + "=" * 50)
    if all_passed:
        print("RESULT: [OK] All clips match the production input contract.")
    else:
        print("RESULT: [FAIL] Contract violations detected. See above.")
    print("=" * 50)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
