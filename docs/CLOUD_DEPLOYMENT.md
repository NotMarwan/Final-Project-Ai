# AI Sentinel Cloud Deployment Guide

## When to Use Cloud

- Your local PC can't run 24/7
- You need remote access to camera feeds
- You want GPU inference without buying a GPU
- You need to scale to multiple simultaneous camera streams

## Option 1: AWS (Recommended for NVIDIA GPU)

### Step 1: Launch GPU Instance

1. Open EC2 Console → Launch Instance
2. Choose AMI: **Deep Learning AMI GPU PyTorch 3.0** (or Ubuntu 22.04)
3. Instance type: **g4dn.xlarge** ($0.526/hr on-demand, ~$0.15/hr spot)
   - 1× NVIDIA T4 GPU (16GB VRAM)
   - 4 vCPU, 16GB RAM
   - NVENC hardware encoder
4. Storage: 100GB gp3
5. Security Group: Allow ports 22 (SSH), 8000 (API), 8001-9000 (WebRTC)

### Step 2: Install Docker with GPU Support

```bash
# Install NVIDIA Container Toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### Step 3: Deploy

```bash
git clone <your-repo-url>
cd ai-sentinel
docker-compose up -d --build
```

### Step 4: Access

- `http://<ec2-public-ip>:8000` — Dashboard
- `http://<ec2-public-ip>:8000/video_feed?camera_id=CAM-01` — Video feed

### Spot Instance (90% Cheaper)

```bash
# Request spot instance with same config
# Set max price to ~$0.15/hr for g4dn.xlarge
# Use persistent request with stop behavior
```

## Option 2: GCP

### Instance Type
- **n1-standard-4** with NVIDIA Tesla T4 attached
- More expensive than AWS for equivalent GPU

### Steps
1. Create VM with GPU quota
2. Install NVIDIA drivers: `sudo apt install nvidia-driver-535`
3. Install Docker + nvidia-container-toolkit
4. Deploy with docker-compose (same as AWS)

## Option 3: Local Server with GPU

If you have a PC with an NVIDIA GPU (RTX 3060 or better):

1. Install Python 3.11+ and CUDA 12.1
2. `pip install -r backend/requirements.txt`
3. `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121`
4. `python backend/api.py`

Your local GPU RTX is often **faster** than cloud GPUs because there's no network overhead for video ingestion.

## Performance Expectations

| Setup | Inference Latency | Stream FPS | Monthly Cost |
|-------|------------------|------------|-------------|
| CPU only (current) | 200-500ms | 3-5 | $0 |
| Local RTX 3060 | 10-25ms | 25-30 | $0 (+elec) |
| AWS g4dn.xlarge | 15-30ms | 25-30 | ~$380 on-demand |
| AWS g4dn.xlarge spot | 15-30ms | 25-30 | ~$110 spot |

## Cost Optimization

- Use **spot instances** for non-critical demos (90% cheaper)
- Use **auto-stop** when not in use (AWS Instance Scheduler)
- Store evidence clips in **S3** with lifecycle policies
- Use **EC2 Image Builder** for pre-baked AMIs to reduce startup time
