# AI Sentinel — Final Checkpoint

**Real-Time AI-Powered Security Surveillance System**

> **This is the final preserved checkpoint.** All three detection pipelines (violence, weapon, multi-threat fusion) are verified working. The overlay system, SSE stream, and live camera feed are all confirmed stable as of 2026-05-18.

Intelligent surveillance platform that detects violence, weapons, and security threats in real-time video feeds using deep learning. Features instant Telegram alerts, a web dashboard, AI forensic reports, and evidence management.

---

## Table of Contents

- [Version History](#version-history)
- [System Overview](#system-overview)
- [Key Features](#key-features)
- [What This Checkpoint Fixes](#what-this-checkpoint-fixes)
- [Quick Start](#quick-start)
- [Manual Setup](#manual-setup)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [Architecture](#architecture)
- [Known Issues & Limitations](#known-issues--limitations)
- [Security](#security)

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v11.0 (Final)** | **2026-05-18** | **Overlay geometry fix, knife/gun label priority, SSE proxy fix, DPR-aware canvas, checkpoint preserved** |
| v10.1 | 2026-05-17 | Directory cleanup, unrelated files organized |
| v10.0 | 2026-05-16 | Student distribution setup, README overhaul |
| v9.0 | 2026-05-16 | Canvas overlay, Docker, cloud deployment |
| v8.0 | 2026-05-07 | Stable Live Alert V2 freeze, Telegram hardening |
| v7.0 | 2026-05-05 | Weapon detection training, YOLOv8 fine-tuning |
| v6.0 | 2026-05-02 | Multi-angle benchmarks, threat latency harness |
| v5.0 | 2026-04-28 | Detection categories expansion, clip sidebar |
| v4.0 | 2026-04-22 | Evidence DVR, forensic reports, face intelligence |
| v3.0 | 2026-04-17 | Telegram alerts, incident reporting, multi-camera |
| v2.0 | 2026-04-13 | Weapon detection engine, threat fusion |
| v1.0 | 2026-04-10 | Violence detection, web dashboard, FastAPI backend |

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   AI SENTINEL — FINAL CHECKPOINT                │
├──────────────────────┬──────────────────────────────────────────┤
│                      │                                          │
│   Frontend (React)   │        Backend (Python FastAPI)          │
│   ─────────────────  │        ─────────────────────────────     │
│   Next.js            │        50+ REST endpoints                │
│   React + TypeScript │        X3D violence detection            │
│   Tailwind CSS       │        YOLO weapon detection             │
│   shadcn/ui          │        Multi-modal threat fusion         │
│                      │        Temporal decision layer V2        │
│   Port: 3000         │        Telegram notifications            │
│                      │        PDF report generation             │
│                      │        Evidence DVR + chain of custody   │
│                      │                                          │
│                      │        Port: 8002 (CUDA GPU)             │
└──────────────────────┴──────────────────────────────────────────┘
```

### Live Endpoints (verified 2026-05-18)

| Service | URL | Status |
|---------|-----|--------|
| Frontend dashboard | `http://localhost:3000` | Running |
| Backend health | `http://localhost:8002/health` | OK |
| SSE alert stream | `http://localhost:8002/alerts` | ONLINE |
| SSE detection stream | `http://localhost:8002/detections?camera_id=CAM-01` | Streaming |
| Live video feed | `http://localhost:8002/video_feed?camera_id=CAM-01` | Active |

---

## Key Features

### AI Detection
- **Violence Detection** — X3D spatiotemporal model, 32-frame rolling window, CUDA GPU
- **Weapon Detection** — YOLO fine-tuned model (pistol, rifle, shotgun, knife, sword, revolver)
- **Multi-Modal Threat Fusion** — Combines violence, motion, and weapon signals into unified severity score
- **Temporal Decision Layer V2** — State machine (NORMAL → WATCH → CONFIRMED → COOLDOWN) requiring 2-of-3 consecutive frames above threshold, eliminating false positives

### Overlay System (fixed in this checkpoint)
- **Object-contain geometry** — Bounding boxes align to the actual rendered video rectangle, not the full container
- **DPR-aware canvas** — Framing quality is isolated from camera pixel density; renders crisp on any screen
- **Dual bbox format** — Supports both pixel-space and normalized (0–1) bounding boxes
- **Knife/gun label priority** — Top-ranked detector label wins; lower-ranked labels no longer override

### Alert System
- **SSE-powered live feed** — 100% stable SSE connection (verified)
- **Telegram Notifications** — Instant alerts with severity filtering
- **Toast notifications** — DEMO/LIVE source badge on every alert

### Dashboard (6 Tabs)
1. **Live Monitor** — Real-time MJPEG video with canvas detection overlays and bounding boxes
2. **Demo Clips** — On-demand video analysis with clip playback
3. **Incidents** — Evidence management with DVR clips and chain of custody
4. **Intelligence** — AI-generated forensic reports (Groq VLM + DeepSeek/OpenRouter)
5. **Operations** — Telegram notification status
6. **System** — SSE link status, connection health, GPU metrics

---

## What This Checkpoint Fixes

These are the exact bugs resolved to reach this checkpoint. **The model weights, thresholds, and detection pipeline were not modified.**

| Bug | Root Cause | Fix |
|-----|-----------|-----|
| Bounding boxes misaligned to video | Overlay scaled against full container instead of `object-contain` video rect | `getContainedVideoRect()` + `projectOverlayBox()` in `lib/live-visual-state.ts` |
| Knife detected as gun | Lower-ranked gun label overrode top-ranked knife label | `classifyWeapon()` now iterates labels in order; first match wins |
| SSE reconnecting / not connected | `next.config.mjs` proxied all routes to port 8000 but backend runs on 8002 | Changed `const backend = 'http://localhost:8000'` → `'http://localhost:8002'` |
| Overlay blurry at high DPI | Canvas sized to CSS pixels, not device pixels | Canvas resized with `devicePixelRatio` scale transform |
| "VIOLENCE" shown on weapon-only alerts | Violence flag latched from inferred threat even when violence was 0.0% | `hasViolence` now requires alert to specifically indicate violence |

### Files changed in this checkpoint

```
next.config.mjs            — proxy port 8000 → 8002 (SSE fix)
components/canvas-overlay.tsx  — overlay geometry uses video fit rect + DPR canvas
lib/live-visual-state.ts   — getContainedVideoRect(), projectOverlayBox() (new)
lib/model-compatibility.ts — classifyWeapon() iterates in label order
backend/fusion.py          — _classify_weapon_type() first-match-wins
components/video-player.tsx — hasViolence only when alert type = violence
```

### What was NOT changed (checkpoint preserved)

```
backend/inference.py           — X3D model weights and pipeline
backend/inference_process.py   — frame processing
backend/live_alert_decision.py — temporal state machine
backend/config.yml             — all thresholds and weights paths
backend/weapon.py              — YOLO inference
best_model.pt                  — violence detection weights
weapon_hadi_yolo.pt            — weapon detection weights
```

---

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 18+

### Backend

```bash
cd "Final Project AI Sentinel/backend"
python -m venv ../venv
../venv/Scripts/activate         # Windows
pip install -r requirements.txt
python api.py
# Backend starts at http://localhost:8002
```

### Frontend

```bash
cd "Final Project AI Sentinel"
npm install
npm run dev
# Dashboard opens at http://localhost:3000
```

### Verify everything is running

```bash
# Backend health
curl http://localhost:8002/health

# SSE alert stream (should emit events)
curl -N http://localhost:8002/alerts

# SSE detection stream for CAM-01
curl -N "http://localhost:8002/detections?camera_id=CAM-01"
```

### Model Weights

The `.pt` files are not committed to the repo (too large for git).

| File | Purpose |
|------|---------|
| `backend/best_model.pt` | Violence detection (X3D) |
| `backend/weapon_hadi_yolo.pt` | Weapon detection (YOLO) |

Without model weights the app starts in **demo mode** — the dashboard and UI work but live AI detection is inactive.

---

## Manual Setup

### Backend `.env`

Create `backend/.env` with:

```env
GROQ_API_KEY=           # AI forensic reports (optional)
OPENROUTER_API_KEY=     # DeepSeek reports (optional)
TELEGRAM_BOT_TOKEN=     # Telegram alerts (optional)
TELEGRAM_CHAT_ID=       # Your Telegram chat ID
```

### Frontend `.env.local`

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8002
NEXT_PUBLIC_SSE_URL=http://localhost:8002/alerts
```

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Backend port | `8002` |
| `HOST` | Backend host | `0.0.0.0` |
| `GROQ_API_KEY` | Groq VLM for forensic reports | — |
| `OPENROUTER_API_KEY` | OpenRouter for DeepSeek reports | — |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | — |
| `TELEGRAM_CHAT_ID` | Telegram chat ID | — |
| `TELEGRAM_MIN_SEVERITY` | Minimum severity for Telegram alerts | `high` |
| `WEIGHTS_PATH` | Violence model path | `best_model.pt` |
| `THRESHOLD` | Model confidence threshold | `0.75` (from config.yml) |
| `WEAPON_WEIGHT_PATH` | YOLO weights path | `./weapon_hadi_yolo.pt` |
| `FACE_INTEL_ENABLED` | Enable face intelligence | `false` |
| `CORS_ORIGINS` | Allowed CORS origins | `http://localhost:3000` |

### Frontend (`.env.local`)

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | Backend base URL | `http://localhost:8002` |
| `NEXT_PUBLIC_SSE_URL` | SSE alert stream URL | `http://localhost:8002/alerts` |

---

## API Endpoints

### System & Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + model status |
| GET | `/system/status` | Combined system status |
| GET | `/system/metrics` | Pipeline performance metrics |
| POST | `/decision_layer/reset` | Reset decision layer state |

### Video Streaming
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/video_feed?camera_id=<id>` | MJPEG video stream |
| GET | `/cameras/status` | Camera status list |

### Alerts & SSE Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/alerts` | SSE stream — real-time alerts |
| GET | `/detections?camera_id=<id>` | SSE stream — detection overlay data |
| POST | `/demo_start/{clip_id}` | Start demo clip analysis |
| DELETE | `/demo_stop/{clip_id}` | Stop demo clip |

### Incidents & Evidence
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/clips/{alert_id}` | Stream recorded incident clip |
| GET | `/api/clips/list` | List incident clips |
| GET | `/download_evidence/{alert_id}` | Download DVR clip |
| GET | `/download_report/{alert_id}` | Download forensic PDF |
| GET | `/evidence_chain/{alert_id}` | Chain of custody |

### Detection Categories
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/categories` | Get detection categories |
| POST | `/api/categories/{id}/toggle` | Toggle category on/off |

### Forensic Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reports/deepseek/status` | DeepSeek service status |
| POST | `/reports/deepseek/{alert_id}` | Generate DeepSeek report |

### Notifications
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/notifications/status` | Notification status |
| POST | `/notifications/telegram/test` | Send test Telegram alert |
| POST | `/notifications/telegram/test_video` | Send test video clip |

### Face Intelligence (disabled by default)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/face/status` | Face intel status |
| GET | `/face/policy` | Get face policy |
| POST | `/face/registry/{person_id}/enroll` | Enroll known person |

---

## Architecture

### Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js, React 19, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Violence Detection | X3D spatiotemporal model (PyTorch), CUDA GPU |
| Weapon Detection | YOLO (ultralytics), fine-tuned |
| Threat Fusion | Multi-modal fusion engine (`fusion.py`) |
| Decision Layer | Temporal state machine V2 (`live_alert_decision.py`) |
| Reports | Groq VLM (Llama 4 Scout), DeepSeek via OpenRouter |
| Notifications | Telegram Bot API |
| PDF Generation | ReportLab + arabic-reshaper + python-bidi |
| Computer Vision | OpenCV, NumPy, PyTorch |
| Container | Docker, NVIDIA CUDA 12.1 |

### Project Structure

```
├── app/                        # Next.js App Router
├── components/
│   ├── canvas-overlay.tsx      # Detection bounding boxes (object-contain geometry)
│   ├── video-player.tsx        # MJPEG video with overlay
│   ├── alert-feed.tsx          # Real-time alert sidebar
│   ├── alert-toast.tsx         # Toast notifications (DEMO/LIVE badge)
│   ├── alert-history.tsx       # Alert history list
│   ├── incident-panel.tsx      # Incident evidence viewer
│   └── dashboard-header.tsx    # Header with SSE status
├── hooks/
│   └── use-detection-stream.ts # SSE detection overlay hook
├── lib/
│   ├── live-visual-state.ts    # getContainedVideoRect, projectOverlayBox
│   └── model-compatibility.ts  # classifyWeapon (label-order-aware)
├── backend/
│   ├── api.py                  # Main FastAPI app (50+ endpoints)
│   ├── inference.py            # X3D violence detection
│   ├── inference_process.py    # Frame processing pipeline
│   ├── weapon.py               # YOLO weapon detection
│   ├── fusion.py               # Multi-modal threat fusion
│   ├── live_alert_decision.py  # Temporal decision layer V2
│   ├── frame_pipeline.py       # Camera capture pipeline
│   ├── pipeline_ai.py          # AI inference pipeline
│   ├── pipeline_render.py      # Annotation rendering
│   ├── visual_annotator.py     # Bounding box annotation
│   ├── person_detector.py      # Person tracking
│   ├── config.yml              # All thresholds and config
│   └── tests/                  # Python test suite
├── tests/
│   └── visual-state.test.mjs   # Overlay geometry regression tests
├── next.config.mjs             # Next.js config (proxy → port 8002)
├── .env.local                  # Frontend env (NEXT_PUBLIC_API_BASE_URL)
└── docker-compose.yml          # Docker orchestration
```

---

## Known Issues & Limitations

### Current Limitations
| Issue | Status | Notes |
|-------|--------|-------|
| No GPU on CPU-only machines | Expected | Inference runs but not real-time. Config auto-falls back to CPU. |
| Face intelligence disabled | By design | Set `face_intel.enabled: true` in `config.yml` to activate |
| Camera profiles disabled | By design | `camera_profiles.yml` has 0 active cameras — relies on webcam or demo clips |
| Weapon detection weights not in repo | By design | `weapon_hadi_yolo.pt` too large for git — share separately |
| WebRTC not active | Not implemented | `go2rtc` bridge is configured but ICE/STUN integration is not complete |

### Resolved in this checkpoint (v11.0)
| Issue | Resolution |
|-------|------------|
| Bounding boxes outside video | Overlay now tracks `object-contain` video rect, not the full container |
| Knife detected as gun | `classifyWeapon()` iterates labels in detector rank order — first match wins |
| SSE reconnecting / OFFLINE | `next.config.mjs` proxy corrected from port 8000 to port 8002 |
| Blurry overlay on high-DPI screens | Canvas resized with `window.devicePixelRatio` — framing quality isolated from camera resolution |
| VIOLENCE shown on weapon-only events | `hasViolence` gate now checks alert type explicitly |
| `forrtl error 200` crash | Caused by Windows CLOSE event on a previous session — current process stable |

---

## Safety Rules

- The red alert is controlled by `confirmed_alert` / `confirmedAlert`, **not** by `model_prediction`
- `model_prediction` is internal telemetry only — never used directly as the alert trigger
- The temporal decision layer requires **2-of-3 consecutive frames** above threshold before an alert fires
- Cooldown is 3 seconds minimum after an alert clears before a new one can be confirmed

## Security

- Never commit `.env` files to version control
- Keep Telegram bot tokens and API keys in `backend/.env` only
- `config.yml` has `api_key: ""` — running in open demo mode; set a key before any production deployment
- Rotate tokens if accidentally exposed
