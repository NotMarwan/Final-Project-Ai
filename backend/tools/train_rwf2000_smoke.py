import argparse
import os
import torch
from torch.utils.data import DataLoader
from datasets.manifest_dataset import ManifestDataset
from datasets.video_contract import get_profile, DEFAULT_PROFILE

def main():
    parser = argparse.ArgumentParser(description="RWF-2000 Training Infrastructure Smoke Test")
    parser.add_argument("--manifest", required=True, help="Path to RWF-2000 JSONL manifest")
    parser.add_argument("--weights", help="Optional path to starting weights")
    parser.add_argument("--max-train-samples", type=int, default=10, help="Limit training samples for smoke test")
    parser.add_argument("--max-val-samples", type=int, default=5, help="Limit validation samples for smoke test")
    parser.add_argument("--epochs", type=int, default=1, help="Number of smoke epochs")
    parser.add_argument("--device", default="cpu", help="Device to run on (cpu, cuda)")
    parser.add_argument("--dry-run", action="store_true", help="Don't run training, just verify data loading")
    parser.add_argument("--real-loader", action="store_true", help="Use real video loader instead of mock")
    parser.add_argument("--profile", default=DEFAULT_PROFILE.name, help="Model profile (legacy_slowfast, x3d)")
    
    args = parser.parse_args()
    
    profile = get_profile(args.profile)
    print(f"[AI] Using model profile: {profile.name}")
    print(f"     Resolution: {profile.resolution}x{profile.resolution}")
    print(f"     Frames: {profile.num_frames}")

    # Use mock loader by default for speed unless --real-loader is set
    loader_fn = None
    if not args.real_loader:
        print("[WARN] Using MOCK loader (random tensors). Use --real-loader for actual video files.")
        def mock_loader(path, profile):
            # Shape: (C, T, H, W)
            return torch.randn(3, profile.num_frames, profile.resolution, profile.resolution)
        loader_fn = mock_loader

    # 1. Setup Datasets
    try:
        train_ds = ManifestDataset(
            manifest_path=args.manifest, 
            split="train", 
            profile=profile,
            loader_fn=loader_fn
        )
        val_ds = ManifestDataset(
            manifest_path=args.manifest, 
            split="val", 
            profile=profile,
            loader_fn=loader_fn
        )
    except Exception as e:
        print(f"[ERROR] Failed to initialize datasets: {e}")
        return

    # Slice for smoke test
    train_ds.samples = train_ds.samples[:args.max_train_samples]
    val_ds.samples = val_ds.samples[:args.max_val_samples]

    print(f"[AI] Train samples: {len(train_ds)}")
    print(f"[AI] Val samples:   {len(val_ds)}")

    # 2. Setup DataLoaders
    train_loader = DataLoader(train_ds, batch_size=2, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=2, shuffle=False)

    # 3. Data Verification
    print("[AI] Verifying data batch shape...")
    try:
        batch_videos, batch_labels = next(iter(train_loader))
        print(f"     Video batch shape: {batch_videos.shape}  (Expected: [B, 3, {profile.num_frames}, {profile.resolution}, {profile.resolution}])")
        print(f"     Label batch shape: {batch_labels.shape}")
        
        # Verify normalization (smoke check)
        if args.real_loader:
            print(f"     Value range: [{batch_videos.min():.2f}, {batch_videos.max():.2f}]")
    except Exception as e:
        print(f"[ERROR] Failed during data loading: {e}")
        return

    if args.dry_run:
        print("[AI] Dry run complete. Infrastructure looks safe.")
        return

    # 4. Model Loading
    print(f"[AI] Preparing model architecture: {profile.model_class}")
    # STUB: In Phase 7G we will implement actual training logic
    print("[WARN] Non-dry-run training not yet implemented. Refusing to modify weights.")
    print("[AI] Mock training phase finished successfully (refused actual update).")

if __name__ == "__main__":
    main()
