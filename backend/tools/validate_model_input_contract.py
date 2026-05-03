import argparse
import torch
import sys
import os
from pathlib import Path
from datasets.manifest_dataset import ManifestDataset
from datasets.video_contract import get_profile, DEFAULT_PROFILE

def main():
    parser = argparse.ArgumentParser(description="Validate model input contract with production weights")
    parser.add_argument("--manifest", required=True, help="Path to JSONL manifest")
    parser.add_argument("--weights", required=True, help="Path to production .pt weights")
    parser.add_argument("--device", default="cpu", help="Device to use")
    parser.add_argument("--samples", type=int, default=1, help="Number of samples to test")
    parser.add_argument("--profile", default=DEFAULT_PROFILE.name, help="Profile to use (legacy_slowfast, x3d)")
    parser.add_argument("--forward-pass", action="store_true", help="Run a no-grad forward pass")

    args = parser.parse_args()

    # Ensure backend is in path
    backend_path = Path(__file__).resolve().parent.parent
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))

    profile = get_profile(args.profile)
    print(f"[AI] Validating contract for profile: {profile.name}")
    print(f"     Resolution: {profile.resolution}x{profile.resolution}")
    print(f"     Target Model: {profile.model_class}")

    # 1. Load Data
    try:
        ds = ManifestDataset(args.manifest, profile=profile)
        print(f"[AI] Loaded manifest with {len(ds)} total samples.")
    except Exception as e:
        print(f"[ERROR] Failed to load manifest: {e}")
        return

    # 2. Test Samples
    print(f"[AI] Testing {args.samples} real samples...")
    for i in range(min(args.samples, len(ds))):
        try:
            video, label = ds[i]
            print(f"     Sample {i}: Shape {video.shape}, Label {label}")
            
            # Basic range check
            print(f"     Value range: [{video.min():.4f}, {video.max():.4f}]")
        except Exception as e:
            print(f"     Sample {i}: [FAIL] {e}")
            continue

    if not args.forward_pass:
        print("[AI] Contract validation complete (data only).")
        return

    # 3. Model Compatibility
    print(f"[AI] Loading production model: {profile.model_class}")
    try:
        if profile.model_class == "ViolenceDetector":
            from inference import ViolenceDetector
            model = ViolenceDetector(num_classes=2).to(args.device)
        elif profile.model_class == "X3DViolenceModel":
            from inference import X3DViolenceModel
            model = X3DViolenceModel(num_classes=2).to(args.device)
        else:
            print(f"[ERROR] Unknown model class in profile: {profile.model_class}")
            return

        # Load weights
        print(f"[AI] Loading weights from: {args.weights}")
        checkpoint = torch.load(args.weights, map_location=args.device, weights_only=False)
        state_dict = checkpoint.get('model_state_dict') or checkpoint.get('state_dict') or checkpoint
        
        # Strip sf. prefix if needed or handle it
        # ViolenceDetector already has self.sf
        model.load_state_dict(state_dict, strict=True)
        print("[AI] Model weights loaded successfully (STRICT MATCH).")

        model.eval()
        with torch.no_grad():
            video, _ = ds[0]
            batch = video.unsqueeze(0).to(args.device)
            print(f"[AI] Running forward pass with batch {batch.shape}...")
            
            if profile.name == "legacy_slowfast":
                # SlowFast needs (slow, fast)
                # ManifestDataset returns (3, 32, 224, 224) -> (C, T, H, W)
                # Legacy SlowFast expects (B, T, C, H, W) in inference.py's legacy path?
                # Actually, our loader returns (C, T, H, W).
                # ViolenceDetector.forward:
                # return self.head(self.sf(slow, fast))
                # SlowFastBackbone.forward rearranges:
                # rearrange(fast, "b t c h w -> b c t h w")
                
                # So we need to provide (B, T, C, H, W)
                fast = batch.permute(0, 2, 1, 3, 4) # (B, C, T, H, W) -> (B, T, C, H, W)
                slow = fast[:, ::4, :, :, :]
                out = model(slow, fast)
            else:
                out = model(batch)
                
            print(f"[AI] Forward pass successful. Output: {out.shape}")
            probs = torch.softmax(out, dim=1)
            print(f"     Probabilities: {probs.cpu().numpy()}")

    except Exception as e:
        print(f"[ERROR] Model compatibility failure: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
