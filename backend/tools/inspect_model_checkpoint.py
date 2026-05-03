import torch
import sys
import argparse
from pathlib import Path

def inspect_checkpoint(weights_path: str):
    p = Path(weights_path)
    if not p.exists():
        print(f"[ERROR] File not found: {weights_path}")
        return

    print(f"==================================================")
    print(f"CHECKPOINT INSPECTION: {p.name}")
    print(f"==================================================")
    
    try:
        # Using map_location='cpu' for safety
        ckpt = torch.load(p, map_location='cpu', weights_only=False)
    except Exception as e:
        print(f"[ERROR] Failed to load checkpoint: {e}")
        return

    print(f"Type: {type(ckpt)}")
    
    state_dict = None
    if isinstance(ckpt, dict):
        print(f"Top-level keys: {list(ckpt.keys())[:30]}")
        # Common keys for state dicts
        state_dict = ckpt.get('model_state_dict') or ckpt.get('state_dict') or ckpt
    else:
        # Check if it's a model object
        print(f"Repr: {repr(ckpt)[:500]}")
        if hasattr(ckpt, 'state_dict'):
            state_dict = ckpt.state_dict()

    if isinstance(state_dict, dict):
        keys = list(state_dict.keys())
        print(f"Tensor count: {len(keys)}")
        
        # Analyze prefixes
        prefixes = set()
        for k in keys:
            parts = k.split('.')
            if len(parts) > 1:
                prefixes.add(parts[0])
        
        print(f"Top-level prefixes: {sorted(list(prefixes))}")
        
        print(f"\nFirst 20 layer shapes:")
        for k in keys[:20]:
            v = state_dict[k]
            if hasattr(v, 'shape'):
                print(f"  {k:40} {tuple(v.shape)}")
            else:
                print(f"  {k:40} [Not a tensor]")
                
        # Check for specific architectures
        is_pytorchvideo = any("blocks" in k for k in keys)
        is_slowfast = any("slow_path" in k or "fast_path" in k for k in keys)
        is_x3d = any("x3d" in k.lower() or ("blocks" in k and len(keys) > 100) for k in keys)
        
        print(f"\nArchitecture Clues:")
        print(f"  PytorchVideo-like: {is_pytorchvideo}")
        print(f"  SlowFast-like:    {is_slowfast}")
        print(f"  X3D-like:         {is_x3d}")
    else:
        print(f"[WARN] No state_dict found or extracted.")

def verify_compatibility(weights_path: str, model_class_name: str):
    print(f"\n" + "-"*50)
    print(f"COMPATIBILITY TEST: {model_class_name}")
    print(f"-"*50)
    
    try:
        # Import target model class
        if model_class_name == "X3DViolenceModel":
            from inference import X3DViolenceModel
            model = X3DViolenceModel(num_classes=2)
        elif model_class_name == "ViolenceDetector":
            from inference import ViolenceDetector
            model = ViolenceDetector(num_classes=2)
        else:
            print(f"[ERROR] Unknown model class: {model_class_name}")
            return

        ckpt = torch.load(weights_path, map_location='cpu', weights_only=False)
        state_dict = ckpt.get('model_state_dict') or ckpt.get('state_dict') or ckpt
        
        if not isinstance(state_dict, dict):
            print(f"[ERROR] Loaded object is not a state_dict.")
            return

        # Attempt load
        missing, unexpected = model.load_state_dict(state_dict, strict=False)
        
        print(f"  Missing keys:    {len(missing)}")
        print(f"  Unexpected keys: {len(unexpected)}")
        
        if len(missing) < 10:
            print(f"  Missing sample:  {missing}")
        if len(unexpected) < 10:
            print(f"  Unexpected sample: {unexpected}")
            
        # Try a forward pass if mostly matched
        if len(unexpected) < len(state_dict) * 0.5:
            print(f"\n  Attempting forward pass (1, 3, 32, 160, 160)...")
            model.eval()
            try:
                with torch.no_grad():
                    if model_class_name == "ViolenceDetector":
                        # SlowFast-style input: (B, T, C, H, W)
                        # Legacy path in inference.py uses resolution 224
                        fast = torch.randn(1, 32, 3, 224, 224)
                        slow = fast[:, ::4, :, :, :]
                        out = model(slow, fast)
                    else:
                        # X3D-style input: (B, C, T, H, W)
                        dummy_input = torch.randn(1, 3, 32, 160, 160)
                        out = model(dummy_input)
                print(f"  [OK] Forward pass successful. Output shape: {tuple(out.shape)}")
            except Exception as e:
                print(f"  [FAIL] Forward pass failed: {e}")
        else:
            print(f"  [SKIP] Too many unexpected keys to attempt forward pass.")
            
    except Exception as e:
        print(f"  [ERROR] Test failed: {e}")

def main():
    parser = argparse.ArgumentParser(description="Inspect model checkpoint architecture")
    parser.add_argument("--weights", default="backend/best_model.pt", help="Path to weights file")
    parser.add_argument("--test-class", help="Optional model class to test compatibility with")
    
    args = parser.parse_args()
    
    # Ensure backend is in path
    backend_path = Path(__file__).resolve().parent.parent
    if str(backend_path) not in sys.path:
        sys.path.insert(0, str(backend_path))
        
    inspect_checkpoint(args.weights)
    
    if args.test_class:
        verify_compatibility(args.weights, args.test_class)

if __name__ == "__main__":
    main()
