# AI Sentinel v10.0

**Real-Time AI-Powered Security Surveillance System**

Intelligent surveillance platform that detects violence, weapons, and security threats in real-time video feeds using deep learning. Features instant Telegram alerts, a web dashboard, AI forensic reports, face intelligence, and evidence management.

---

## Table of Contents

- [Version History](#version-history)
- [System Overview](#system-overview)
- [Key Features](#key-features)
- [Advantages](#advantages)
- [Known Issues & Limitations](#known-issues--limitations)
- [Quick Start (Students)](#quick-start-students)
- [Manual Setup](#manual-setup)
- [Docker Deployment](#docker-deployment)
- [Environment Variables](#environment-variables)
- [API Endpoints](#api-endpoints)
- [Architecture](#architecture)
- [Documentation Index](#documentation-index)
- [License](#license)

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v10.0** | 2026-05-16 | Student distribution setup, port standardization, README overhaul |
| v9.0 | 2026-05-16 | WebRTC streaming (Phase 1), Canvas overlay, Docker, cloud deployment |
| v8.0 | 2026-05-07 | Stable Live Alert V2 freeze, preservation manifests, Telegram hardening |
| v7.0 | 2026-05-05 | Weapon detection training, YOLOv8 fine-tuning, backpressure safety |
| v6.0 | 2026-05-02 | Multi-angle benchmarks, threat latency harness, intrusion detection |
| v5.0 | 2026-04-28 | Detection categories expansion, clip sidebar, lint/typecheck gates |
| v4.0 | 2026-04-22 | Evidence DVR, forensic reports, face intelligence, audit logging |
| v3.0 | 2026-04-17 | Telegram alerts, incident reporting, multi-camera support |
| v2.0 | 2026-04-13 | Weapon detection engine, threat fusion, audio analysis |
| v1.0 | 2026-04-10 | Initial commit — violence detection, web dashboard, FastAPI backend |

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI SENTINEL v10.0                        │
├──────────────────────┬──────────────────────────────────────────┤
│                      │                                          │
│   Frontend (React)   │        Backend (Python FastAPI)          │
│   ─────────────────  │        ─────────────────────────────     │
│   Next.js 16         │        50+ REST endpoints                │
│   React 19           │        X3D violence detection            │
│   Tailwind CSS 4     │        YOLOv8 weapon detection           │
│   shadcn/ui          │        Face intelligence engine          │
│   Recharts           │        Multi-modal threat fusion         │
│                      │        Temporal decision layer V2        │
│   Ports: 3000        │        Telegram notifications            │
│                      │        PDF report generation (Arabic/EN) │
│                      │        Evidence DVR + chain of custody    │
│                      │        Audio distress detection          │
│                      │        Go2rtc WebRTC bridge              │
│                      │                                          │
│                      │        Port: 8002                        │
├──────────────────────┴──────────────────────────────────────────┤
│  Platforms: Web · Electron Desktop · Capacitor Android · Docker │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Features

### AI Detection
- **Violence Detection** — X3D spatiotemporal deep learning model, 32-frame rolling window, ~96% accuracy
- **Weapon Detection** — YOLOv8s fine-tuned model (pistol, rifle, shotgun, knife, sword, revolver)
- **Face Intelligence** — Custom face recognition with IoU tracking, known-person registry, identity labeling, and audit trail
- **Audio Analysis** — Scream/distress detection via audio signal analysis
- **Multi-Modal Threat Fusion** — Combines violence, motion, and weapon signals into unified severity score

### Alert System
- **Live Alert Decision Layer V2** — Temporal state machine (NORMAL → WATCH → CONFIRMED → COOLDOWN) requiring 2-of-3 consecutive frames above threshold to confirm alerts, eliminating false positives
- **Real-Time Dashboard** — SSE-powered live alert feed with detection overlays
- **Telegram Notifications** — Instant alerts to security personnel with severity filtering
- **Detection Categories** — Violence, weapon, firearms, threat, panic, danger, intrusion

### Dashboard (6 Tabs)
1. **Live Monitor** — Real-time video with canvas detection overlays and bounding boxes
2. **Demo Clips** — On-demand video analysis with clip playback
3. **Incidents** — Evidence management with DVR clips, thumbnails, and chain of custody
4. **Intelligence** — AI-generated forensic reports (Groq VLM + DeepSeek/OpenRouter)
5. **Operations** — Geo-map dashboard and Telegram notification status
6. **System** — Health metrics, GPU status, pipeline performance

### Infrastructure
- **WebRTC Streaming** — Low-latency streaming via go2rtc (Phase 1)
- **Docker Support** — NVIDIA CUDA 12.1 container with GPU passthrough
- **Cloud Deployment** — AWS GPU instance support (g4dn.xlarge)
- **Multi-Platform** — Web, Electron desktop, Capacitor Android
- **Student Distribution** — One-command setup scripts (setup.bat / start.bat / stop.bat)

---

## Advantages

### Technical Strengths
1. **False-positive elimination** — The V2 temporal decision layer prevents phantom alerts by requiring multi-frame confirmation before triggering
2. **Multi-modal fusion** — Combines visual (violence + weapon) and audio signals for higher detection accuracy than single-model approaches
3. **Real-time performance** — Decoupled capture/inference pipeline, GPU auto-detection, configurable JPEG quality, and fast annotation mode
4. **Full audit trail** — Every detection, alert, and face recognition event is logged with chain of custody for forensic integrity
5. **Arabic + English support** — PDF reports and AI forensic analysis generated in both languages

### Operational Strengths
6. **Zero-config demo mode** — App runs without model weights or API keys; dashboard and UI fully functional
7. **One-command student setup** — `setup.bat` + `start.bat` gets any Windows machine running in minutes
8. **Multi-platform deployment** — Same codebase runs on web, desktop (Electron), mobile (Capacitor), and Docker
9. **Modular backend** — 50+ REST endpoints with clean separation of concerns (detection, fusion, notifications, reporting, evidence)
10. **Extensive documentation** — 30+ docs covering API reference, troubleshooting, deployment, training, and demo procedures

### Research Strengths
11. **Reproducible benchmarks** — Threat latency benchmarks, multi-angle evaluation protocols, and external dataset validation
12. **Training pipeline** — Colab-compatible notebooks for YOLOv8 weapon fine-tuning with RWF-2000 dataset
13. **Model policy** — Strict preservation freeze protocol ensures reproducibility for thesis evaluation

---

## Known Issues & Limitations

### Critical
| Issue | Status | Notes |
|-------|--------|-------|
| `best_model.pt` SHA mismatch | **Open** | Local model file does not match documented stable runtime SHA. Verify before live demos. |
| No GPU on CPU-only machines | **Expected** | Inference runs but significantly slower. No real-time performance on CPU. |

### Moderate
| Issue | Status | Notes |
|-------|--------|-------|
| WebRTC Phase 1 incomplete | **In Progress** | go2rtc bridge configured but full ICE/STUN integration pending |
| Face intel disabled by default | **By Design** | Requires `FACE_INTEL_ENABLED=true` and face detector backend setup |
| Weapon detection weights not in repo | **By Design** | `.pt` files too large for git. Must be shared separately. |
| Camera profiles disabled | **By Design** | All cameras set to `enabled: false`. No real cameras connected in demo mode. |

### Minor
| Issue | Status | Notes |
|-------|--------|-------|
| Frontend hook tests empty | **Open** | `hooks/__tests__/` directory exists but has no test files |
| No version pinning in requirements.txt | **Open** | Only `openai>=1.0.0` is pinned. May cause compatibility issues with future releases. |
| Cloudflare tunnel binary not in repo | **By Design** | `cloudflared-windows-amd64.exe` is gitignored. Must be downloaded separately. |

### Resolved in v10.0
| Issue | Resolution |
|-------|------------|
| Port mismatch (8000 vs 8002) | Standardized to port 8002 across all configs and scripts |
| No student setup scripts | Added setup.bat, start.bat, stop.bat |
| README disorganized | Complete rewrite with table of contents, version history, and categorized sections |

---

## Quick Start (Students)

### Prerequisites
- [Python 3.10+](https://www.python.org/downloads/) — check "Add to PATH" during install
- [Node.js 18+](https://nodejs.org/)
- Git

### Steps

```bash
# 1. Clone the repository
git clone https://github.com/NotMarwan/Final-Project-Ai.git
cd Final-Project-Ai

# 2. Run one-time setup (installs all dependencies)
setup.bat

# 3. Edit API keys (optional — demo mode works without them)
#    Open backend\.env and fill in:
#    - GROQ_API_KEY (AI forensic reports)
#    - OPENROUTER_API_KEY (DeepSeek reports)
#    - TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (Telegram alerts)

# 4. Launch the application
start.bat
# Opens at http://localhost:3000

# 5. Stop when done
stop.bat
```

### Updating

After new changes are pushed:
```bash
git pull
start.bat
```

### Model Weights

The `.pt` files are not in the repo (too large). Without them, the app runs in **demo mode** — the dashboard works but AI detection is disabled.

| File | Purpose | Required? |
|------|---------|-----------|
| `backend/best_model.pt` | Violence detection (X3D) | Only for live detection |
| `backend/weapon_yolo.pt` | Weapon detection (YOLOv8) | Only for live detection |

Get these from the shared drive or contact the team lead. Place them in `backend/`.

---

## Manual Setup

### Backend

```bash
# Create virtual environment
python -m venv backend/venv
backend/venv/Scripts/activate        # Windows
# source backend/venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r backend/requirements.txt

# Create environment file
cp backend/.env.example backend/.env
# Edit backend/.env with your settings

# Start server
cd backend
python -m uvicorn api:app --host 0.0.0.0 --port 8002 --reload
```

### Frontend

```bash
# Install dependencies
npm install

# Create environment file
cp .env.local.example .env.local

# Start dev server
npm run dev
# Opens at http://localhost:3000
```

---

## Docker Deployment

```bash
docker-compose up -d --build
```

Requires NVIDIA Container Toolkit for GPU passthrough. See [Cloud Deployment Guide](docs/CLOUD_DEPLOYMENT.md) for AWS GPU instance setup.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Backend server port | `8002` |
| `HOST` | Backend server host | `0.0.0.0` |
| `ADMIN_API_KEY` | Admin API key for protected endpoints | `CHANGE_ME_BEFORE_DEMO` |
| `GROQ_API_KEY` | Groq API key for VLM forensic reports | - |
| `OPENROUTER_API_KEY` | OpenRouter API key for DeepSeek reports | - |
| `OPENROUTER_MODEL` | OpenRouter model name | `deepseek/deepseek-chat-v3.1` |
| `OPENROUTER_BASE_URL` | OpenRouter base URL | `https://openrouter.ai/api/v1` |
| `TELEGRAM_ENABLED` | Enable Telegram alerts | `false` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | - |
| `TELEGRAM_CHAT_ID` | Chat ID for alerts | - |
| `TELEGRAM_MIN_SEVERITY` | Minimum severity for alerts | `high` |
| `WEIGHTS_PATH` | Path to violence detection model | `best_model.pt` |
| `THRESHOLD` | Model confidence threshold | `0.51` |
| `STRIDE` | Inference stride (frames) | `16` |
| `WEAPON_BACKEND` | Weapon detection backend (`yolo` / `torchvision_coco`) | `yolo` |
| `WEAPON_WEIGHT_PATH` | YOLO weights path | `./weapon_yolo.pt` |
| `WEAPON_LABELS` | Weapon classes to detect | `pistol,knife` |
| `FACE_INTEL_ENABLED` | Enable face intelligence | `false` |
| `FACE_DETECTOR_BACKEND` | Face detector backend | `none` |
| `DATABASE_PATH` | SQLite database path | `./sentinel.db` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |
| `GO2RTC_PORT` | go2rtc WebRTC port | `1984` |

### Frontend (`.env.local`)

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API base URL | `http://localhost:8002` |
| `NEXT_PUBLIC_SSE_URL` | SSE alert stream URL | `http://localhost:8002/alerts` |
| `NEXT_PUBLIC_WS_URL` | WebSocket URL | `ws://localhost:8002/ws` |
| `NEXT_PUBLIC_ADMIN_API_KEY` | Admin API key for frontend requests | `sentinel-demo-2026` |

---

## API Endpoints

### System & Health
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/system/status` | Combined system status |
| GET | `/system/metrics` | Pipeline performance metrics |
| POST | `/decision_layer/reset` | Reset decision layer state |

### Video Streaming
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/video_feed?camera_id=<id>` | MJPEG video stream |
| GET | `/api/webrtc/{cam_id}` | WebRTC stream metadata |
| POST | `/api/webrtc/{cam_id}/whep` | Proxy WHEP SDP offer |
| GET | `/cameras/status` | Camera status list |

### Alerts & Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/alerts` | SSE event stream (real-time alerts) |
| GET | `/detections` | SSE detection metadata stream |
| POST | `/demo_start/{clip_id}` | Start demo clip analysis |
| DELETE | `/demo_stop/{clip_id}` | Stop demo clip analysis |

### Incidents & Evidence
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/clips/{alert_id}` | Stream recorded incident clip |
| GET | `/api/clips/list` | List available incident clips |
| GET | `/download_evidence/{alert_id}` | Fetch DVR clip |
| GET | `/download_report/{alert_id}` | Fetch forensic PDF report |
| GET | `/evidence_chain/{alert_id}` | Evidence chain of custody |

### Detection Categories
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/categories` | Get all detection categories |
| POST | `/api/analyze` | Analyze frame for specific category |
| POST | `/api/categories/{category_id}/toggle` | Toggle category on/off |

### Forensic Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reports/deepseek/status` | DeepSeek service status |
| POST | `/reports/deepseek/{alert_id}` | Generate DeepSeek report |

### Notifications
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/notifications/status` | Notification subsystem status |
| POST | `/notifications/telegram/test` | Send test Telegram alert |

### Face Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/face/status` | Face intelligence status |
| GET | `/face/policy` | Get face policy |
| POST | `/face/policy` | Update face policy |
| GET | `/face/registry` | List known people |
| POST | `/face/registry/{person_id}/enroll` | Enroll known person |

### Audio
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/audio/status` | Audio analysis status |
| POST | `/audio/analyze` | Analyze audio for distress |

### Security & Audit
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/security/status` | Access control status |
| GET | `/audit/recent` | Recent audit events |

---

## Architecture

### Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui |
| Backend | Python 3.10+, FastAPI, Uvicorn |
| Violence Detection | X3D spatiotemporal model (PyTorch) |
| Weapon Detection | YOLOv8s (ultralytics) |
| Face Recognition | Custom engine with IoU tracking |
| Threat Fusion | Multi-modal fusion engine |
| Reports | Groq VLM (Llama 4 Scout), DeepSeek/OpenRouter |
| Notifications | Telegram Bot API |
| PDF Generation | ReportLab + arabic-reshaper + python-bidi |
| Computer Vision | OpenCV, NumPy, PyTorch, torchvision |
| Desktop | Electron 33 |
| Mobile | Capacitor 8 (Android) |
| Container | Docker, NVIDIA CUDA 12.1 |

### Project Structure

```
├── app/                    # Next.js App Router (dashboard, layout, globals)
├── components/             # React components (22 files)
│   ├── video-player.tsx    # MJPEG/WebRTC video with overlays
│   ├── canvas-overlay.tsx  # Detection bounding box canvas
│   ├── alert-feed.tsx      # Real-time alert sidebar
│   ├── incident-panel.tsx  # Incident details + evidence
│   ├── ai-report.tsx       # AI forensic report display
│   ├── command-palette.tsx # Cmd+K command palette
│   └── ui/                 # shadcn/ui base components
├── hooks/                  # Custom React hooks
│   ├── use-detection-stream.ts  # SSE detection overlay
│   └── use-clip-playback.ts     # Video clip playback
├── lib/                    # Utilities, types, shared data
├── backend/                # Python FastAPI server (~2500 lines)
│   ├── api.py              # Main application (50+ endpoints)
│   ├── inference.py        # X3D violence detection pipeline
│   ├── weapon.py           # YOLO weapon detection engine
│   ├── face_intel.py       # Face recognition engine
│   ├── fusion.py           # Multi-modal threat fusion
│   ├── live_alert_decision.py  # Temporal decision layer V2
│   ├── notifications.py    # Telegram notification service
│   ├── reporting.py        # PDF report generation
│   ├── evidence.py         # Evidence DVR and clips
│   ├── security.py         # Access control + audit logging
│   ├── audio.py            # Audio risk analyzer
│   ├── config.yml          # Centralized configuration
│   └── tests/              # 30 Python test files
├── scripts/                # Utility scripts (14 files)
├── docs/                   # Documentation (34 files)
├── desktop/                # Electron desktop wrapper
├── android/                # Capacitor Android app
├── docker-compose.yml      # Docker orchestration
├── Dockerfile              # NVIDIA CUDA build
├── setup.bat               # Student one-time setup
├── start.bat               # Launch both servers
└── stop.bat                # Stop both servers
```

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [Project Status](docs/00_PROJECT_STATUS.md) | Current freeze status and runtime reference |
| [Runtime Restore Guide](docs/01_RUNTIME_RESTORE_GUIDE.md) | Colab runtime restore checklist |
| [Live Alert Decision Layer V2](docs/02_LIVE_ALERT_DECISION_LAYER_V2.md) | Temporal confirmation state machine |
| [Stage 12 External Eval](docs/03_STAGE12_EXTERNAL_EVAL.md) | External dataset evaluation results |
| [Demo Runbook](docs/04_DEMO_RUNBOOK.md) | Pre-demo checklist and procedures |
| [Troubleshooting](docs/05_TROUBLESHOOTING.md) | Common issues and solutions |
| [Model and Data Policy](docs/06_MODEL_AND_DATA_POLICY.md) | Preservation and backup policies |
| [Telegram Alerts](docs/07_TELEGRAM_ALERTS.md) | Complete Telegram configuration |
| [API Reference](docs/API_REFERENCE.md) | Full endpoint documentation (50+) |
| [Environment Variables](docs/ENV_VARS.md) | Master env var reference |
| [Frontend Components](docs/FRONTEND_COMPONENTS.md) | Component catalog and data flow |
| [Cloud Deployment](docs/CLOUD_DEPLOYMENT.md) | AWS GPU instance deployment |
| [Weapon Detection Setup](docs/WEAPON_DETECTION_SETUP.md) | YOLO weapon configuration |
| [Training Plan](docs/TRAINING_PLAN.md) | Weapon detection model training |
| [Video Performance](docs/VIDEO_PERFORMANCE_OVERHAUL_DESIGN.md) | Performance optimization designs |
| [Changelog](CHANGELOG.md) | Full project history |
| [Project Overview](PROJECT_DOCUMENTATION.md) | Architecture overview |

---

## Safety Rules

- The visible red alert is controlled by `confirmed_alert` / `confirmedAlert`, **not** by `model_prediction`
- `model_prediction` is internal runtime telemetry only
- See [Live Alert Decision Layer V2](docs/02_LIVE_ALERT_DECISION_LAYER_V2.md) for the full state machine

## Security

- Never commit `.env` files to version control
- Keep Telegram bot tokens and API keys secret
- Use `.env.example` as template
- Rotate tokens if accidentally exposed
- Change `ADMIN_API_KEY` before any demo

---

## License

[Add your license information here]
