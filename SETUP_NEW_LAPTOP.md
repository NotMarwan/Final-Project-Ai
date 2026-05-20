# AI-Sentinel — Setup Guide for New Laptop (Windows)

This guide will get AI-Sentinel running on a fresh Windows laptop from scratch.  
**Estimated time:** 20–30 minutes (plus model download time).

---

## Step 1 — Install Git

1. Download Git from: https://git-scm.com/download/win
2. Run the installer with default settings.
3. Open **PowerShell** or **Command Prompt** and verify:
   ```
   git --version
   ```
   You should see something like `git version 2.x.x`.

---

## Step 2 — Install Git LFS

Git LFS handles the large model weights and demo video files.

1. Download from: https://git-lfs.com
2. Run the installer.
3. In PowerShell, verify:
   ```
   git lfs version
   ```
   You should see `git-lfs/3.x.x`.

---

## Step 3 — Clone the Branch

```powershell
git clone --branch final-demo-transfer https://github.com/NotMarwan/Final-Project-Ai.git "AI-Sentinel"
cd "AI-Sentinel"
```

---

## Step 4 — Download LFS Files (Model Weights + Demo Videos)

```powershell
git lfs pull
```

This downloads:
- `backend/best_model.pt` (~142 MB) — violence detection
- `backend/weapon_hadi_yolo.pt` (~6 MB) — weapon detection  
- `demo_assets/videos/` — 3 demo clips (~32 MB total)

**Note:** This requires an internet connection. If you see authentication errors, you may need to log in to GitHub.

---

## Step 5 — Install Python

1. Download Python 3.10 or newer from: https://www.python.org/downloads/
2. During installation, **check "Add Python to PATH"**.
3. Verify:
   ```
   python --version
   ```

---

## Step 6 — Install Node.js

1. Download Node.js 18 LTS or newer from: https://nodejs.org/
2. Run the installer with default settings.
3. Verify:
   ```
   node --version
   npm --version
   ```

---

## Step 7 — (Optional) Install NVIDIA CUDA

Only needed if the laptop has an NVIDIA GPU and you want GPU-accelerated inference.

- Download CUDA 12.1 from: https://developer.nvidia.com/cuda-12-1-0-download-archive
- Install the NVIDIA driver matching your GPU.
- Without CUDA, the system falls back to CPU mode (slower, but functional).

---

## Step 8 — Create Python Virtual Environment

```powershell
cd "AI-Sentinel"
python -m venv venv
venv\Scripts\activate
```

Your prompt should now show `(venv)`.

---

## Step 9 — Install Backend Dependencies

```powershell
cd backend
pip install -r requirements.txt
cd ..
```

This takes a few minutes. If you have a GPU, PyTorch with CUDA will be installed.

---

## Step 10 — Install Frontend Dependencies

```powershell
npm install
```

This downloads all Node.js packages (~1,000 packages, normal for Next.js).

---

## Step 11 — Configure Environment Variables

Copy the example files and fill in your real keys:

```powershell
# Backend secrets
Copy-Item backend\.env.example backend\.env
notepad backend\.env

# Frontend config (usually no changes needed for local demo)
Copy-Item .env.local.example .env.local
```

In `backend\.env`, fill in:
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
GROQ_API_KEY=your_groq_api_key
```

**Note:** The system runs in demo mode without Telegram/Groq keys. You only need those for live alerts and AI reports.

---

## Step 12 — Start the Backend

Open **PowerShell Window 1**:

```powershell
cd "AI-Sentinel\backend"
..\venv\Scripts\activate
python api.py
```

Wait for:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8002
```

Verify it works:
```powershell
curl http://localhost:8002/health
```

---

## Step 13 — Start the Frontend

Open **PowerShell Window 2**:

```powershell
cd "AI-Sentinel"
npm run dev
```

Wait for:
```
▲ Next.js 14.x.x
- Local: http://localhost:3000
```

---

## Step 14 — Open the Dashboard

Open your browser and go to:
```
http://localhost:3000
```

You should see the AI-Sentinel dark dashboard with 6 tabs.

---

## Step 15 — Run a Demo Clip

1. Click the **Demo Clips** tab in the dashboard.
2. Select **EXAMPLE-01**, **EXAMPLE-02**, or **EXAMPLE-03**.
3. Click **Start Analysis**.
4. Watch the confidence gauge rise and the detection overlay appear.
5. When the Decision Layer confirms a threat, check the **Incidents** tab for the evidence clip.

---

## Quick-Start Alternative — Use the Setup Scripts

Instead of steps 8–13, you can use the provided PowerShell scripts:

```powershell
# One-time setup (creates venv and installs everything)
.\setup_windows.ps1

# Start backend (in one PowerShell window)
.\run_backend.ps1

# Start frontend (in another PowerShell window)
.\run_frontend.ps1
```

---

## Troubleshooting

| Problem | Solution |
|---------|---------|
| `best_model.pt` missing | Run `git lfs pull` in the project folder |
| Demo videos missing | Run `git lfs pull` — videos are in LFS |
| Backend port already in use | Change `PORT=8002` in `backend/.env` and update `NEXT_PUBLIC_API_BASE_URL` in `.env.local` |
| `ModuleNotFoundError` | Make sure venv is active: `venv\Scripts\activate` |
| Dashboard shows no video | Check backend is running on port 8002 |
| GPU not detected | Install NVIDIA CUDA 12.1 + matching driver |
| `npm install` fails | Make sure Node.js 18+ is installed |

---

## Summary — What You Need

| Requirement | Version |
|-------------|---------|
| Git | 2.x |
| Git LFS | 3.x |
| Python | 3.10+ |
| Node.js | 18+ |
| NVIDIA CUDA (optional) | 12.1 |

The demo works on CPU without a GPU. Detection will be slower but fully functional.
