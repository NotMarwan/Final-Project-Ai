# Activate RTX 3060 GPU for AI Sentinel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace CPU-only PyTorch with CUDA-enabled PyTorch 2.3.0 so AI Sentinel uses the NVIDIA RTX 3060 GPU for inference, reducing latency from ~500ms to ~50ms and enabling smooth real-time camera streaming.

**Architecture:** Uninstall existing CPU-only torch/torchvision/torchaudio packages, reinstall CUDA 11.8 compatible versions matching requirements.txt (torch==2.3.0), verify GPU detection via PyTorch and device_utils, confirm AI Sentinel backend initializes models on cuda:0.

**Tech Stack:** Python 3.14, PyTorch 2.3.0+cu118, NVIDIA Driver 591.86, CUDA 13.1 (backward compatible), Windows 10/11 PowerShell

---

## File Structure

| File | Role |
|------|------|
| `backend/requirements.txt` | Source of truth for package versions |
| `backend/device_utils.py` | GPU detection utility (already exists) |
| `backend/device_config.py` | Optimal device selector (already exists) |
| `backend/tests/test_device_utils.py` | Existing device tests |
| `backend/tests/test_gpu_activation.py` | **NEW** - Verification test for GPU activation |
| `scripts/verify_gpu.py` | **NEW** - Standalone GPU verification script |

---

## Task 1: Backup Current Environment State

**Files:**
- Read: `backend/requirements.txt`
- Create: `backups/2026-05-17-pre-gpu-upgrade.txt`

- [ ] **Step 1: Document current PyTorch state**

Run:
```powershell
Set-Location "C:\Users\PCD\Downloads\Final Project AI Sentinel"
python -c "import torch; print('Version:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

Expected output:
```
Version: 2.11.0+cpu
CUDA: False
Device: CPU
```

- [ ] **Step 2: Save pip freeze snapshot**

Run:
```powershell
New-Item -ItemType Directory -Force -Path "backups"
pip freeze | Out-File -FilePath "backups\2026-05-17-pre-gpu-upgrade.txt" -Encoding utf8
```

Verify:
```powershell
Select-String -Path "backups\2026-05-17-pre-gpu-upgrade.txt" -Pattern "torch"
```

Expected: Shows `torch==2.11.0` (or similar CPU version)

- [ ] **Step 3: Commit backup**

```bash
git add backups/2026-05-17-pre-gpu-upgrade.txt
git commit -m "chore: backup pip state before GPU upgrade"
```

---

## Task 2: Uninstall CPU-Only PyTorch Packages

**Files:**
- Modify: System Python packages

- [ ] **Step 1: Uninstall torch, torchvision, torchaudio, pytorchvideo**

Run:
```powershell
pip uninstall torch torchvision torchaudio pytorchvideo -y
```

Expected output:
```
Found existing installation: torch 2.11.0
Uninstalling torch-2.11.0:
Successfully uninstalled torch-2.11.0
...
```

- [ ] **Step 2: Verify uninstallation**

Run:
```powershell
python -c "import torch"
```

Expected output:
```
ModuleNotFoundError: No module named 'torch'
```

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "chore: uninstall CPU-only PyTorch packages"
```

---

## Task 3: Install CUDA-Enabled PyTorch 2.3.0

**Files:**
- Modify: System Python packages

- [ ] **Step 1: Install torch==2.3.0 with CUDA 11.8**

Run:
```powershell
pip install torch==2.3.0 torchvision==0.18.0 torchaudio==2.3.0 --index-url https://download.pytorch.org/whl/cu118
```

Expected output (excerpt):
```
Successfully installed torch-2.3.0+cu118 torchvision-0.18.0+cu118 torchaudio-2.3.0+cu118
```

**Note:** Download is ~2.5GB. This will take 5-15 minutes depending on internet speed.

- [ ] **Step 2: Verify CUDA torch installation**

Run:
```powershell
python -c "import torch; print('Version:', torch.__version__); print('CUDA:', torch.cuda.is_available())"
```

Expected output:
```
Version: 2.3.0+cu118
CUDA: True
```

- [ ] **Step 3: Verify GPU is accessible**

Run:
```powershell
python -c "import torch; print('Device:', torch.cuda.get_device_name(0)); print('VRAM:', torch.cuda.get_device_properties(0).total_memory / 1e9, 'GB')"
```

Expected output:
```
Device: NVIDIA GeForce RTX 3060
VRAM: 12.0 GB
```

- [ ] **Step 4: Reinstall pytorchvideo**

Run:
```powershell
pip install pytorchvideo
```

- [ ] **Step 5: Commit**

```bash
git commit --allow-empty -m "feat: install PyTorch 2.3.0 with CUDA 11.8 for RTX 3060"
```

---

## Task 4: Create GPU Verification Test

**Files:**
- Create: `backend/tests/test_gpu_activation.py`
- Create: `scripts/verify_gpu.py`

- [ ] **Step 1: Write test_gpu_activation.py**

```python
"""Tests to verify GPU activation for AI Sentinel."""
import pytest
import torch


def test_pytorch_is_cuda_version():
    """Ensure PyTorch is built with CUDA support."""
    assert torch.cuda.is_available(), "PyTorch CUDA is not available"
    assert "cuda" in torch.__version__ or "cu" in torch.__version__, f"Expected CUDA PyTorch, got: {torch.__version__}"


def test_rtx_3060_detected():
    """Verify RTX 3060 is detected and accessible."""
    assert torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0)
    assert "RTX 3060" in device_name, f"Expected RTX 3060, got: {device_name}"


def test_device_utils_returns_cuda():
    """Verify device_utils selects CUDA over CPU."""
    from device_utils import get_device, is_gpu_available, get_device_name
    
    device = get_device()
    assert device.type == "cuda", f"Expected cuda device, got: {device.type}"
    assert is_gpu_available() is True
    assert "RTX 3060" in get_device_name()


def test_device_config_returns_cuda():
    """Verify device_config selects optimal GPU."""
    from device_config import get_optimal_device
    
    device = get_optimal_device(prefer_gpu=True)
    assert device.type == "cuda", f"Expected cuda, got: {device.type}"
    assert device.index == 0


def test_vram_sufficient():
    """Verify GPU has enough VRAM for AI Sentinel models."""
    assert torch.cuda.is_available()
    total_vram = torch.cuda.get_device_properties(0).total_memory
    min_required = 4 * 1024**3  # 4GB minimum
    assert total_vram >= min_required, f"VRAM {total_vram / 1e9:.1f}GB < required 4GB"


def test_cuda_tensor_operations():
    """Verify basic CUDA tensor operations work."""
    device = torch.device("cuda:0")
    tensor = torch.randn(1000, 1000, device=device)
    result = tensor @ tensor.T
    assert result.device.type == "cuda"
```

- [ ] **Step 2: Write scripts/verify_gpu.py**

```python
#!/usr/bin/env python3
"""Standalone script to verify GPU activation for AI Sentinel.

Run this after installing CUDA PyTorch to confirm everything works.
"""
import sys


def verify_gpu():
    print("=" * 60)
    print("AI Sentinel GPU Verification")
    print("=" * 60)
    
    # 1. Check PyTorch
    try:
        import torch
        print(f"\n✓ PyTorch installed: {torch.__version__}")
    except ImportError:
        print("\n✗ PyTorch not installed!")
        return False
    
    # 2. Check CUDA availability
    if not torch.cuda.is_available():
        print("✗ CUDA not available - PyTorch is CPU-only!")
        print("  Solution: Reinstall PyTorch with CUDA support")
        return False
    
    print(f"✓ CUDA available: {torch.cuda.is_available()}")
    
    # 3. Check GPU name
    device_name = torch.cuda.get_device_name(0)
    print(f"✓ GPU detected: {device_name}")
    
    # 4. Check VRAM
    props = torch.cuda.get_device_properties(0)
    vram_gb = props.total_memory / 1e9
    print(f"✓ VRAM: {vram_gb:.1f} GB")
    
    # 5. Check device_utils
    try:
        from device_utils import get_device, get_device_name, is_gpu_available
        device = get_device()
        print(f"✓ device_utils.get_device(): {device}")
        print(f"✓ device_utils.get_device_name(): {get_device_name()}")
        print(f"✓ device_utils.is_gpu_available(): {is_gpu_available()}")
    except Exception as e:
        print(f"✗ device_utils failed: {e}")
        return False
    
    # 6. Check device_config
    try:
        from device_config import get_optimal_device
        optimal = get_optimal_device(prefer_gpu=True)
        print(f"✓ device_config.get_optimal_device(): {optimal}")
    except Exception as e:
        print(f"✗ device_config failed: {e}")
        return False
    
    # 7. Test CUDA tensor
    try:
        tensor = torch.randn(100, 100, device="cuda:0")
        result = tensor.sum()
        print(f"✓ CUDA tensor test passed: sum={result.item():.2f}")
    except Exception as e:
        print(f"✗ CUDA tensor test failed: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("✓ ALL CHECKS PASSED - GPU is ready for AI Sentinel!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = verify_gpu()
    sys.exit(0 if success else 1)
```

- [ ] **Step 3: Run verification script**

Run:
```powershell
Set-Location "C:\Users\PCD\Downloads\Final Project AI Sentinel"
python scripts/verify_gpu.py
```

Expected output:
```
============================================================
AI Sentinel GPU Verification
============================================================

✓ PyTorch installed: 2.3.0+cu118
✓ CUDA available: True
✓ GPU detected: NVIDIA GeForce RTX 3060
✓ VRAM: 12.0 GB
✓ device_utils.get_device(): cuda
✓ device_utils.get_device_name(): NVIDIA GeForce RTX 3060
✓ device_utils.is_gpu_available(): True
✓ device_config.get_optimal_device(): cuda:0
✓ CUDA tensor test passed: sum=...

============================================================
✓ ALL CHECKS PASSED - GPU is ready for AI Sentinel!
============================================================
```

- [ ] **Step 4: Run pytest on GPU tests**

Run:
```powershell
Set-Location "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -m pytest tests/test_gpu_activation.py -v
```

Expected output:
```
test_gpu_activation.py::test_pytorch_is_cuda_version PASSED
test_gpu_activation.py::test_rtx_3060_detected PASSED
test_gpu_activation.py::test_device_utils_returns_cuda PASSED
test_gpu_activation.py::test_device_config_returns_cuda PASSED
test_gpu_activation.py::test_vram_sufficient PASSED
test_gpu_activation.py::test_cuda_tensor_operations PASSED
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_gpu_activation.py scripts/verify_gpu.py
git commit -m "test: add GPU activation verification tests and script"
```

---

## Task 5: Verify Existing Tests Still Pass

**Files:**
- Read: `backend/tests/test_device_utils.py`
- Modify: None (should already pass)

- [ ] **Step 1: Run existing device tests**

Run:
```powershell
Set-Location "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -m pytest tests/test_device_utils.py -v
```

Expected output:
```
test_device_utils.py::test_get_device_returns_torch_device PASSED
test_device_utils.py::test_get_device_returns_valid_type PASSED
test_device_utils.py::test_device_name_returns_string PASSED
test_device_utils.py::test_is_gpu_returns_bool PASSED
test_device_utils.py::test_get_onnx_providers_returns_list PASSED
```

**Note:** `test_get_device_returns_valid_type` should now return `"cuda"` instead of `"cpu"`.

- [ ] **Step 2: Run all backend tests**

Run:
```powershell
Set-Location "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -m pytest tests/ -v --tb=short
```

Expected: All tests pass (or known failures documented).

- [ ] **Step 3: Commit**

```bash
git commit --allow-empty -m "test: verify all tests pass with CUDA PyTorch"
```

---

## Task 6: Update Documentation

**Files:**
- Read: `docs/VIDEO_PERFORMANCE_OVERHAUL_PLAN.md`
- Create: `docs/GPU_SETUP.md`

- [ ] **Step 1: Create GPU setup documentation**

```markdown
# GPU Setup Guide - AI Sentinel

## Verified Hardware

- **GPU:** NVIDIA GeForce RTX 3060 (12GB VRAM)
- **Driver:** 591.86+
- **CUDA:** 13.1 (backward compatible with PyTorch CUDA 11.8)
- **PyTorch:** 2.3.0+cu118

## Installation

### Step 1: Verify GPU Detection

```powershell
nvidia-smi
```

Expected output shows RTX 3060 with driver version.

### Step 2: Install CUDA-Enabled PyTorch

```powershell
pip uninstall torch torchvision torchaudio -y
pip install torch==2.3.0 torchvision==0.18.0 torchaudio==2.3.0 --index-url https://download.pytorch.org/whl/cu118
```

### Step 3: Verify Installation

```powershell
python scripts/verify_gpu.py
```

### Step 4: Run AI Sentinel

```powershell
cd backend
python api.py
```

Expected log output:
```
[Device] CUDA GPU: NVIDIA GeForce RTX 3060, 12.0 GB VRAM
[CAM-01] AI Engine initializing on cuda:0...
```

## Troubleshooting

### "CUDA not available" after installation

1. Verify NVIDIA driver: `nvidia-smi`
2. Check PyTorch version: `python -c "import torch; print(torch.__version__)"`
3. Should show `2.3.0+cu118` not `+cpu`
4. If still failing, reinstall: `pip install --force-reinstall torch==2.3.0+cu118`

### Out of Memory (OOM) errors

RTX 3060 has 12GB VRAM. AI Sentinel models use ~2-4GB.
If OOM occurs:
- Reduce batch size in `config.yml`
- Close other GPU applications
- Check VRAM usage: `nvidia-smi`

## Performance Expectations

| Metric | CPU Mode | GPU Mode (RTX 3060) |
|--------|----------|-------------------|
| Inference Latency | 500-1000ms | 30-80ms |
| Stream FPS | 5-10 FPS | 25-30 FPS |
| CPU Usage | 80-100% | 15-30% |
| GPU VRAM Usage | N/A | 2-4 GB |
```

- [ ] **Step 2: Commit documentation**

```bash
git add docs/GPU_SETUP.md
git commit -m "docs: add GPU setup guide for RTX 3060"
```

---

## Task 7: Final Verification with AI Sentinel Backend

**Files:**
- Modify: None (read-only verification)

- [ ] **Step 1: Check AI Sentinel detects GPU at startup**

Run:
```powershell
Set-Location "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -c "from device_config import get_optimal_device; d = get_optimal_device(True); print(f'Device: {d}')"
```

Expected output:
```
[Device] CUDA GPU: NVIDIA GeForce RTX 3060, 12.0 GB VRAM
Device: cuda:0
```

- [ ] **Step 2: Start backend and confirm GPU initialization**

Run:
```powershell
Set-Location "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python api.py
```

Wait for initialization logs. Expected:
```
[System] Loaded X camera(s) from ...
[Engines] Importing dependencies...
[Engines] Dependencies imported.
[CAM-01] AI Engine initializing on cuda:0...
[AI] Initializing X3D-M on cuda:0...
[AI] X3D model loaded successfully.
```

**Note:** Do not run full backend if camera is not available. Just verify the logs show `cuda:0` instead of `cpu`.

- [ ] **Step 3: Stop backend (Ctrl+C)**

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: activate RTX 3060 GPU for AI Sentinel inference

- Replace CPU-only PyTorch 2.11.0 with CUDA 11.8 PyTorch 2.3.0
- GPU inference reduces latency from ~500ms to ~50ms
- Add verification tests and standalone check script
- Document GPU setup process"
```

---

## Self-Review Checklist

### Spec Coverage
- [x] Uninstall CPU PyTorch (Task 2)
- [x] Install CUDA PyTorch 2.3.0 (Task 3)
- [x] Verify GPU detection (Task 4)
- [x] Test device_utils/device_config (Task 4, 5)
- [x] Verify existing tests pass (Task 5)
- [x] Document setup (Task 6)
- [x] Final backend verification (Task 7)

### Placeholder Scan
- [x] No "TBD", "TODO", "implement later"
- [x] No vague "add error handling" without specifics
- [x] No "write tests for the above" without test code
- [x] No "similar to Task N" references
- [x] All steps have exact commands and expected outputs

### Type Consistency
- [x] `torch.device("cuda:0")` used consistently
- [x] `device.type == "cuda"` check used in tests
- [x] File paths match actual project structure

### Rollback Plan
If anything goes wrong:
```powershell
pip uninstall torch torchvision torchaudio -y
pip install -r backups/2026-05-17-pre-gpu-upgrade.txt
```

---

## Summary

| Task | Duration | Purpose |
|------|----------|---------|
| Task 1: Backup | 2 min | Safety net for rollback |
| Task 2: Uninstall | 2 min | Remove CPU PyTorch |
| Task 3: Install CUDA PyTorch | 10-15 min | Download + install 2.5GB |
| Task 4: Verification Tests | 5 min | Confirm GPU works |
| Task 5: Existing Tests | 3 min | No regressions |
| Task 6: Documentation | 5 min | Future reference |
| Task 7: Backend Check | 3 min | Final confirmation |

**Total Time:** ~30-35 minutes (mostly download time)

**Expected Result:** AI Sentinel runs on RTX 3060 with 10x faster inference, enabling smooth real-time camera streaming.
