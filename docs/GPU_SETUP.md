# GPU Setup Guide - AI Sentinel

## Verified Hardware

- **GPU:** NVIDIA GeForce RTX 3060 (12GB VRAM)
- **Driver:** 591.86+
- **CUDA:** 13.1 (backward compatible with PyTorch CUDA 11.8)
- **PyTorch:** 2.3.0+cu118
- **Python:** 3.12.5 (via venv)

## Installation

### Prerequisites

1. Ensure NVIDIA driver is installed:
   ```powershell
   nvidia-smi
   ```

2. Ensure Python 3.12 is available:
   ```powershell
   py -3.12 --version
   ```

### Step 1: Create Virtual Environment

```powershell
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel"
py -3.12 -m venv venv
```

### Step 2: Install CUDA-Enabled PyTorch

Download the CUDA wheels manually (due to large file size):

1. **torch** (2.6GB): 
   ```
   https://download.pytorch.org/whl/cu118/torch-2.3.0%2Bcu118-cp312-cp312-win_amd64.whl
   ```

2. **torchvision** (5MB):
   ```
   https://download.pytorch.org/whl/cu118/torchvision-0.18.0%2Bcu118-cp312-cp312-win_amd64.whl
   ```

3. **torchaudio** (4MB):
   ```
   https://download.pytorch.org/whl/cu118/torchaudio-2.3.0%2Bcu118-cp312-cp312-win_amd64.whl
   ```

Then install:
```powershell
.\venv\Scripts\pip.exe install torch-2.3.0+cu118-cp312-cp312-win_amd64.whl
.\venv\Scripts\pip.exe install torchvision-0.18.0+cu118-cp312-cp312-win_amd64.whl
.\venv\Scripts\pip.exe install torchaudio-2.3.0+cu118-cp312-cp312-win_amd64.whl
```

### Step 3: Install Remaining Dependencies

```powershell
.\venv\Scripts\pip.exe install pytorchvideo
.\venv\Scripts\pip.exe install -r backend/requirements.txt
```

### Step 4: Verify Installation

```powershell
.\venv\Scripts\python.exe scripts/verify_gpu.py
```

Expected output:
```
[OK] PyTorch installed: 2.3.0+cu118
[OK] CUDA available: True
[OK] GPU detected: NVIDIA GeForce RTX 3060
[OK] VRAM: 12.9 GB
[OK] ALL CHECKS PASSED - GPU is ready for AI Sentinel!
```

### Step 5: Run AI Sentinel

```powershell
cd backend
..\venv\Scripts\python.exe api.py
```

Expected log output:
```
[Device] CUDA GPU: NVIDIA GeForce RTX 3060, 12.9 GB VRAM
[CAM-01] AI Engine initializing on cuda:0...
```

## Troubleshooting

### "CUDA not available" after installation

1. Verify NVIDIA driver: `nvidia-smi`
2. Check PyTorch version: `.\venv\Scripts\python.exe -c "import torch; print(torch.__version__)"`
3. Should show `2.3.0+cu118` not `+cpu`
4. If still failing, reinstall: `.\venv\Scripts\pip.exe install --force-reinstall torch-2.3.0+cu118-cp312-cp312-win_amd64.whl`

### NumPy Warning: "_ARRAY_API not found"

This is a known compatibility issue between PyTorch 2.3.0 and NumPy 2.x.
Solution: Downgrade NumPy to 1.x:
```powershell
.\venv\Scripts\pip.exe install "numpy<2"
```

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

## Virtual Environment Usage

Always activate the venv before running AI Sentinel:

```powershell
# Activate venv
.\venv\Scripts\activate

# Run backend
cd backend
python api.py

# Deactivate when done
deactivate
```

Or use the venv Python directly:
```powershell
.\venv\Scripts\python.exe backend/api.py
```
