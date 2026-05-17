#!/usr/bin/env python3
"""Standalone script to verify GPU activation for AI Sentinel.

Run this after installing CUDA PyTorch to confirm everything works.
"""
import sys
import os

# Add backend directory to path for imports
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


def verify_gpu():
    print("=" * 60)
    print("AI Sentinel GPU Verification")
    print("=" * 60)
    
    # 1. Check PyTorch
    try:
        import torch
        print(f"\n[OK] PyTorch installed: {torch.__version__}")
    except ImportError:
        print("\n[FAIL] PyTorch not installed!")
        return False
    
    # 2. Check CUDA availability
    if not torch.cuda.is_available():
        print("[FAIL] CUDA not available - PyTorch is CPU-only!")
        print("  Solution: Reinstall PyTorch with CUDA support")
        return False
    
    print(f"[OK] CUDA available: {torch.cuda.is_available()}")
    
    # 3. Check GPU name
    device_name = torch.cuda.get_device_name(0)
    print(f"[OK] GPU detected: {device_name}")
    
    # 4. Check VRAM
    props = torch.cuda.get_device_properties(0)
    vram_gb = props.total_memory / 1e9
    print(f"[OK] VRAM: {vram_gb:.1f} GB")
    
    # 5. Check device_utils
    try:
        from device_utils import get_device, get_device_name, is_gpu_available
        device = get_device()
        print(f"[OK] device_utils.get_device(): {device}")
        print(f"[OK] device_utils.get_device_name(): {get_device_name()}")
        print(f"[OK] device_utils.is_gpu_available(): {is_gpu_available()}")
    except Exception as e:
        print(f"[FAIL] device_utils failed: {e}")
        return False
    
    # 6. Check device_config
    try:
        from device_config import get_optimal_device
        optimal = get_optimal_device(prefer_gpu=True)
        print(f"[OK] device_config.get_optimal_device(): {optimal}")
    except Exception as e:
        print(f"[FAIL] device_config failed: {e}")
        return False
    
    # 7. Test CUDA tensor
    try:
        tensor = torch.randn(100, 100, device="cuda:0")
        result = tensor.sum()
        print(f"[OK] CUDA tensor test passed: sum={result.item():.2f}")
    except Exception as e:
        print(f"[FAIL] CUDA tensor test failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("[OK] ALL CHECKS PASSED - GPU is ready for AI Sentinel!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = verify_gpu()
    sys.exit(0 if success else 1)
