import argparse
import sys
import torch
from pathlib import Path

# Add backend to path if run from root
sys.path.insert(0, str(Path(__file__).parent.parent))

from datasets.manifest_dataset import ManifestDataset
from training.train_config import TrainConfig
from inference import X3DViolenceModel

def parse_args():
    parser = argparse.ArgumentParser(description="Smoke Training for RWF-2000")
    parser.add_argument("--manifest", required=True, help="Path to manifest JSONL")
    parser.add_argument("--weights", default="backend/best_model.pt", help="Path to initial weights")
    parser.add_argument("--max-train-samples", type=int, default=None, help="Max train samples")
    parser.add_argument("--max-val-samples", type=int, default=None, help="Max val samples")
    parser.add_argument("--epochs", type=int, default=1, help="Number of epochs")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="auto", help="Device to use")
    parser.add_argument("--dry-run", action="store_true", help="Only validate data loading, do not train")
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Initialize Config
    config = TrainConfig(
        manifest_path=args.manifest,
        weights_path=args.weights,
        max_train_samples=args.max_train_samples,
        max_val_samples=args.max_val_samples,
        epochs=args.epochs,
        device=args.device,
        output_dir=".runlogs/training/smoke" # will be modified by validate() to add timestamp
    )
    
    config.validate()
    
    print("\n" + "="*40)
    print("RWF-2000 SMOKE TRAINING INITIALIZATION")
    print("="*40)
    print(f"Manifest:   {config.manifest_path}")
    print(f"Weights:    {config.weights_path}")
    print(f"Device:     {config.device}")
    print(f"Output Dir: {config.output_dir}")
    print(f"Dry Run:    {args.dry_run}")
    print("-" * 40)
    
    # Load Datasets
    print("Loading datasets...")
    try:
        train_dataset = ManifestDataset(
            manifest_path=config.manifest_path, 
            split="train", 
            max_samples=config.max_train_samples
        )
        val_dataset = ManifestDataset(
            manifest_path=config.manifest_path, 
            split="val", 
            max_samples=config.max_val_samples
        )
    except Exception as e:
        print(f"[ERROR] Failed to load datasets: {e}")
        sys.exit(1)
        
    print(f"Train samples: {len(train_dataset)}")
    print(f"Val samples:   {len(val_dataset)}")
    
    # Analyze labels
    train_labels = [str(e.get("label", "")).lower() for e in train_dataset.entries]
    val_labels = [str(e.get("label", "")).lower() for e in val_dataset.entries]
    
    print("\nLabel Distribution:")
    print(f"Train: Normal={train_labels.count('normal')}, Violence={train_labels.count('violence')}")
    print(f"Val:   Normal={val_labels.count('normal')}, Violence={val_labels.count('violence')}")
    
    if args.dry_run:
        print("\n[DRY RUN] Validating data loader only...")
        # Validate that we can grab an item
        if len(train_dataset) > 0:
            try:
                item = train_dataset[0]
                print(f"Successfully loaded one train item: shape {item['video'].shape}, label {item['label']}")
            except Exception as e:
                print(f"[ERROR] Data loading failed: {e}")
                sys.exit(1)
        print("\n[DRY RUN] Completed successfully. No training performed.")
        return

    print("\nInitializing model...")
    # This acts as a safe stub for the future full training
    # We do not perform actual training loop yet.
    print("[WARN] Actual model training loop is not yet integrated with the production weights.")
    print("[WARN] Aborting full training to protect best_model.pt until Phase 7C fine-tuning loop is fully tested.")
    print("Please use --dry-run for infrastructure validation.")

if __name__ == "__main__":
    main()
