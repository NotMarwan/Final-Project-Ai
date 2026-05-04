import argparse
import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from pathlib import Path
from datetime import datetime
import json
import time

from datasets.manifest_dataset import ManifestDataset
from datasets.video_contract import get_profile, DEFAULT_PROFILE
from inference import ViolenceDetector

def train_one_epoch(model, loader, optimizer, criterion, device):
    model.train()
    running_loss = 0.0
    correct = 0
    total = 0
    
    print(f"[Train] Starting epoch on {device}...")
    for i, (videos, labels) in enumerate(loader):
        videos, labels = videos.to(device), labels.to(device)
        
        # Pathway split for SlowFast (Legacy)
        # Slow: 8 frames, Fast: 32 frames
        slow = videos[:, :, ::4, :, :].permute(0, 2, 1, 3, 4)
        fast = videos.permute(0, 2, 1, 3, 4)
        
        optimizer.zero_grad()
        outputs = model(slow, fast)
        
        # ViolenceDetector output is [B, 6] but RWF is binary
        # We take the first 2 classes or just map the output
        # Based on best_model.pt audit, indices 0 and 1 represent normal/violence
        logits = outputs[:, :2]
        
        loss = criterion(logits, labels)
        loss.backward()
        optimizer.step()
        
        running_loss += loss.item()
        _, predicted = logits.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()
        
        if (i + 1) % 5 == 0 or i == len(loader) - 1:
            print(f"      Batch {i+1}/{len(loader)} - Loss: {loss.item():.4f}")
            
    return running_loss / len(loader), 100.0 * correct / total

def validate(model, loader, criterion, device):
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0
    
    with torch.no_grad():
        for videos, labels in loader:
            videos, labels = videos.to(device), labels.to(device)
            slow = videos[:, :, ::4, :, :].permute(0, 2, 1, 3, 4)
            fast = videos.permute(0, 2, 1, 3, 4)
            
            outputs = model(slow, fast)
            logits = outputs[:, :2]
            
            loss = criterion(logits, labels)
            running_loss += loss.item()
            _, predicted = logits.max(1)
            total += labels.size(0)
            correct += predicted.eq(labels).sum().item()
            
    return running_loss / len(loader), 100.0 * correct / total

def is_production_path(path: Path) -> bool:
    try:
        target_abs = Path("backend/best_model.pt").resolve()
        return path.resolve() == target_abs
    except Exception:
        return str(path).endswith("best_model.pt")

def save_smoke_checkpoint(model, optimizer, epoch, config, metrics, output_dir):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(output_dir) / f"smoke_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    
    checkpoint_path = run_dir / "smoke_checkpoint.pt"
    
    # SAFETY: Never overwrite production weights
    if is_production_path(checkpoint_path):
        raise RuntimeError("CRITICAL ERROR: Attempted to overwrite production weights!")
        
    torch.save({
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'config': config,
        'metrics': metrics,
        'source_weights': config.get("weights_path")
    }, checkpoint_path)
    
    # Save a summary JSON
    with open(run_dir / "summary.json", "w") as f:
        json.dump(metrics, f, indent=2)
        
    return checkpoint_path

def main():
    parser = argparse.ArgumentParser(description="RWF-2000 Training Infrastructure Smoke Test")
    parser.add_argument("--manifest", required=True, help="Path to RWF-2000 JSONL manifest")
    parser.add_argument("--weights", help="Optional path to starting weights")
    parser.add_argument("--max-train-samples", type=int, default=4, help="Limit training samples for smoke test (max 8)")
    parser.add_argument("--max-val-samples", type=int, default=2, help="Limit validation samples for smoke test (max 8)")
    parser.add_argument("--epochs", type=int, default=1, help="Number of smoke epochs (max 1)")
    parser.add_argument("--device", default="auto", help="Device to run on (cpu, cuda, auto)")
    parser.add_argument("--dry-run", action="store_true", help="Don't run training, just verify data loading")
    parser.add_argument("--real-loader", action="store_true", help="Use real video loader instead of mock")
    parser.add_argument("--profile", default=DEFAULT_PROFILE.name, help="Model profile (legacy_slowfast, x3d)")
    parser.add_argument("--output-dir", default=".runlogs/training/smoke", help="Directory to save checkpoints")
    
    args = parser.parse_args()
    
    # 0. Safety Checks
    if not args.dry_run:
        if args.max_train_samples > 8:
            print("[ERROR] Safety cap: max_train_samples must be <= 8 for smoke training.")
            return
        if args.epochs > 1:
            print("[ERROR] Safety cap: epochs must be <= 1 for smoke training.")
            return
        if not args.weights:
             print("[WARN] No weights provided. Training from random initialization.")

    profile = get_profile(args.profile)
    if profile.name != "legacy_slowfast" and not args.dry_run:
        print(f"[ERROR] Actual training loop currently only supports 'legacy_slowfast' (ViolenceDetector). Requested: {profile.name}")
        return

    print(f"[AI] Using model profile: {profile.name}")
    
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device)
    print(f"[AI] Using device: {device}")

    # Use mock loader by default for speed unless --real-loader is set
    loader_fn = None
    if not args.real_loader:
        print("[WARN] Using MOCK loader (random tensors). Use --real-loader for actual video files.")
        def mock_loader(path, profile):
            return torch.randn(3, profile.num_frames, profile.resolution, profile.resolution)
        loader_fn = mock_loader

    # 1. Setup Datasets
    try:
        train_ds = ManifestDataset(manifest_path=args.manifest, split="train", profile=profile, loader_fn=loader_fn)
        val_ds = ManifestDataset(manifest_path=args.manifest, split="val", profile=profile, loader_fn=loader_fn)
    except Exception as e:
        print(f"[ERROR] Failed to initialize datasets: {e}")
        return

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
        print(f"     Video batch shape: {batch_videos.shape}")
        if args.real_loader:
            print(f"     Value range: [{batch_videos.min():.2f}, {batch_videos.max():.2f}]")
    except Exception as e:
        print(f"[ERROR] Failed during data loading: {e}")
        return

    if args.dry_run:
        print("[AI] Dry run complete. Infrastructure looks safe.")
        return

    # 4. Model & Training
    print(f"[AI] Initializing model: {profile.model_class}")
    model = ViolenceDetector(num_classes=2).to(device)
    
    if args.weights:
        print(f"[AI] Loading weights from: {args.weights}")
        try:
            checkpoint = torch.load(args.weights, map_location=device)
            state_dict = checkpoint.get("model_state_dict", checkpoint)
            model.load_state_dict(state_dict, strict=False)
            print("     Weights loaded successfully.")
        except Exception as e:
            print(f"     [WARN] Could not load weights: {e}")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=1e-4)

    start_time = time.time()
    train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
    val_loss, val_acc = validate(model, val_loader, criterion, device)
    duration = time.time() - start_time

    metrics = {
        "train_loss": train_loss,
        "train_acc": train_acc,
        "val_loss": val_loss,
        "val_acc": val_acc,
        "duration_sec": duration,
        "profile": profile.name,
        "timestamp": datetime.now().isoformat()
    }

    print(f"\n[AI] Smoke Training Results:")
    print(f"     Train Loss: {train_loss:.4f} | Acc: {train_acc:.2f}%")
    print(f"     Val Loss:   {val_loss:.4f} | Acc: {val_acc:.2f}%")
    print(f"     Duration:   {duration:.2f}s")

    # 5. Checkpointing
    config = {
        "max_train_samples": args.max_train_samples,
        "max_val_samples": args.max_val_samples,
        "epochs": args.epochs,
        "profile": profile.name,
        "weights_path": args.weights
    }
    
    try:
        cp_path = save_smoke_checkpoint(model, optimizer, 1, config, metrics, args.output_dir)
        print(f"\n[AI] Checkpoint saved: {cp_path}")
    except Exception as e:
        print(f"[ERROR] Failed to save checkpoint: {e}")

    print("[AI] Tiny smoke training phase finished successfully.")

if __name__ == "__main__":
    main()
