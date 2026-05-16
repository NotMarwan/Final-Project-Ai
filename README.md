# AI-Sentinel Surveillance System

AI-Sentinel is an intelligent surveillance system that uses AI to detect violence, weapons, and security threats in real-time video feeds. The system provides instant Telegram alerts, a web-based dashboard, comprehensive incident reporting with forensic AI analysis (Groq VLM & DeepSeek/OpenRouter), face intelligence, and evidence management.

## Features

- **Real-time Violence Detection**: AI-powered detection of violent behavior in video feeds using X3D spatiotemporal architecture
- **Weapon Detection**: YOLOv8-based weapon detection (pistol, rifle, shotgun, knife, sword, revolver) - see [Weapon Detection Setup](docs/WEAPON_DETECTION_SETUP.md) and [Training Plan](docs/TRAINING_PLAN.md)
- **Danger Alert System**: Detects dangerous situations automatically via multi-modal threat fusion
- **Face Intelligence**: Face recognition, known-person registry, identity labeling, and audit trail - see [Face Policy API](backend/api.py)
- **Telegram Alerts**: Instant notifications sent to security personnel via Telegram
- **Web Dashboard**: Modern React-based interface for monitoring cameras and alerts
- **Incident Reporting**: Automated report generation for security incidents
- **AI Forensic Reports**: Groq VLM and DeepSeek/OpenRouter-generated incident descriptions in Arabic and English
- **Multi-Camera Support**: Monitor multiple camera feeds simultaneously
- **Evidence Capture**: Automatic clip recording and thumbnail generation
- **Live Alert Decision Layer V2**: Multi-signal temporal confirmation with WATCH/CONFIRMED/COOLDOWN state machine
- **WebRTC Streaming**: Low-latency streaming via go2rtc (Phase 1 - see [WebRTC Plan](docs/superpowers/plans/2026-05-16-phase1-webrtc-streaming.md))
- **Detection Categories**: Categorized detection system (violence, weapon, firearms, threat, panic, danger, intrusion)
- **Audio Analysis**: Scream/distress detection (configurable)
- **Performance Metrics**: GPU auto-detection, configurable JPEG quality, fast annotation mode, decoupled capture/inference

## Current Stable Runtime Reference

- `FINAL_LIVE_ALERT_API_CHECK: PASS`
- `SAFE_TO_RUN_LIVE_DEMO: True`
- `VIOLENCE_CLS = 1`
- Live Alert Decision Layer V2 is the intended stable decision policy.
- Stable runtime reference model SHA256:
  `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`
- Workspace-local `backend/best_model.pt` SHA256 at freeze time:
  `1fb38eeb54821d827a4621ac3fce4ad98488bc05fbf99df9ab78a13ed223b6cb`

Important: the local `backend/best_model.pt` file in this workspace does not match the documented stable runtime SHA above. Treat the documented SHA as the reference for Colab restore and verify the canonical model file before the next live demo.

## Safety Rule

The visible red alert must be controlled by `confirmed_alert` / `confirmedAlert`, not by `model_prediction`. `model_prediction` is internal runtime telemetry only. See [Live Alert Decision Layer V2](docs/02_LIVE_ALERT_DECISION_LAYER_V2.md).

## Project Layout

```
├── app/                    # Next.js App Router pages (monitor, demo-clips, incidents, etc.)
├── components/             # React components (video player, alert feed, incident panel, etc.)
│   └── ui/                 # shadcn/ui base components (button, card, dialog, etc.)
├── hooks/                  # Custom React hooks (use-detection-stream, use-clip-playback, etc.)
├── lib/                    # Utility functions, shared data models, detection types
├── public/                 # Static assets, icons, logos
├── styles/                 # Global CSS and utilities
├── backend/                # Python FastAPI server
│   ├── api.py              # Main FastAPI application (~2500 lines, all routes)
│   ├── inference.py        # X3D violence detection inference pipeline
│   ├── weapon.py           # Weapon detection engine (YOLO + torchvision fallback)
│   ├── face_intel.py       # Face recognition and intelligence engine
│   ├── fusion.py           # Multi-modal threat fusion engine
│   ├── live_alert_decision.py  # Temporal alert decision layer V2
│   ├── notifications.py    # Telegram notification service
│   ├── reporting.py        # PDF incident report generation
│   ├── evidence.py         # Evidence DVR and clip management
│   ├── security.py         # Access control and audit logging
│   ├── audio.py            # Audio risk analyzer (scream/distress)
│   ├── detection_categories.py  # Categorized detection system
│   ├── go2rtc_bridge.py    # go2rtc sidecar management for WebRTC
│   ├── config.yml          # Centralized configuration
│   ├── best_model.pt       # Model weights (see SHA warning above)
│   └── camera_profiles.yml # Camera source definitions
├── scripts/                # Utility scripts (setup, training, testing)
├── notebooks/              # Jupyter/Colab notebooks
├── docs/                   # Documentation
├── manifests/              # Preservation manifests
├── reports/                # Freeze reports and summaries
├── desktop/                # Electron desktop wrapper
├── android/                # Capacitor Android app
├── docker-compose.yml      # Docker deployment
└── Dockerfile              # Docker build
```

## Quick Start

### Student Setup (Windows — Recommended)

For team members who cloned the repo and want to run the project:

1. **Prerequisites**: Install [Python 3.10+](https://www.python.org/downloads/) and [Node.js 18+](https://nodejs.org/). Check "Add to PATH" during Python install.

2. **Clone the repo**:
   ```bash
   git clone <repo-url>
   cd "Final Project AI Sentinel"
   ```

3. **Run setup** (one time only):
   ```
   setup.bat
   ```
   This installs all Python and Node.js dependencies and creates config files.

4. **Edit API keys** (optional — demo mode works without them):
   Open `backend\.env` and fill in your keys:
   - `GROQ_API_KEY` — for AI forensic reports
   - `OPENROUTER_API_KEY` — for DeepSeek reports
   - `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — for Telegram alerts

5. **Launch**:
   ```
   start.bat
   ```
   The app opens at http://localhost:3000

6. **Stop**:
   ```
   stop.bat
   ```

### Updating

After new changes are pushed:
```bash
git pull
start.bat
```

### Model Weights

The `.pt` model files are not in the repo (too large). If you need AI detection:
- `backend/best_model.pt` — violence detection model
- `backend/weapon_yolo.pt` — weapon detection model

Get these from the shared drive or contact the team lead. Place them in `backend/`.

Without model weights, the app runs in **demo mode** — the dashboard works but AI detection is disabled.

---

### Backend Setup (Manual)

1. Copy the environment file:
   ```bash
   cp backend/.env.example backend/.env
   ```

2. Configure your settings in `backend/.env` (see [Environment Variables](#environment-variables) below)

3. Install dependencies:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. Start the backend:
   ```bash
   cd backend
   python api.py
   ```
   Or with uvicorn:
   ```bash
   cd backend
   python -m uvicorn api:app --host 0.0.0.0 --port 8002 --reload
   ```

### Frontend Setup

1. Install dependencies:
   ```bash
   npm install
   ```

2. Create `.env.local` from `.env.local.example`:
   ```bash
   cp .env.local.example .env.local
   ```

3. Start the dev server:
   ```bash
   npm run dev
   ```

4. Open [http://localhost:3000](http://localhost:3000)

### Docker Deployment

```bash
docker-compose up -d --build
```

See [Cloud Deployment Guide](docs/CLOUD_DEPLOYMENT.md) for production deployment on AWS GPU instances.

## Environment Variables

### Backend (`backend/.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `GROQ_API_KEY` | Groq API key for VLM forensic reports | - |
| `OPENROUTER_API_KEY` | OpenRouter API key for DeepSeek reports | - |
| `OPENROUTER_MODEL` | OpenRouter model name | `deepseek/deepseek-chat-v3.1` |
| `OPENROUTER_BASE_URL` | OpenRouter base URL | `https://openrouter.ai/api/v1` |
| `TELEGRAM_ENABLED` | Enable Telegram alerts | `false` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather | - |
| `TELEGRAM_CHAT_ID` | Chat ID for alerts | - |
| `TELEGRAM_TIMEOUT_SECONDS` | API timeout | `8.0` |
| `TELEGRAM_MIN_ALERT_INTERVAL_SECONDS` | Min interval between alerts | `60` |
| `TELEGRAM_SEND_TEST_ON_STARTUP` | Send test on startup | `false` |
| `TELEGRAM_MIN_SEVERITY` | Minimum severity for alerts | `high` |
| `ADMIN_API_KEY` | Admin API key for protected endpoints | `CHANGE_ME_BEFORE_DEMO` |
| `WEIGHTS_PATH` | Path to model weights | `best_model.pt` |
| `THRESHOLD` | Model confidence threshold | `0.75` |
| `STRIDE` | Inference stride (frames) | `16` |
| `PORT` | Backend server port | `8002` |
| `HOST` | Backend server host | `0.0.0.0` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |
| `DATABASE_PATH` | SQLite database path | `./sentinel.db` |
| `THUMBNAILS_DIR` | Thumbnails directory | `./thumbnails` |
| `EVIDENCE_DIR` | Evidence clips directory | `./evidence_clips` |
| `AI_SENTINEL_ENABLE_CAPTURE_LOOP` | Enable live capture loop | `true` |
| `CAMERA_PROFILES_PATH` | Camera profiles config | `camera_profiles.yml` |
| `DEFAULT_CAMERA_ID` | Default camera ID | `CAM-01` |
| `FACE_INTEL_ENABLED` | Enable face intelligence | `false` |
| `FACE_DETECTOR_BACKEND` | Face detector backend | `none` |
| `FACE_KNOWN_MATCH_THRESHOLD` | Known face match threshold | `0.45` |
| `FACE_KNOWN_MIN_CONFIDENCE` | Known face min confidence | `0.52` |
| `FACE_REGISTRY_PATH` | Known faces registry path | `./known_faces_registry.json` |
| `FACE_POLICY_OVERRIDES_PATH` | Policy overrides path | `./face_policy_overrides.json` |
| `WEAPON_BACKEND` | Weapon detection backend (`yolo` or `torchvision_coco`) | `yolo` |
| `WEAPON_WEIGHT_PATH` | YOLO weights path | `./weapon_yolo.pt` |
| `WEAPON_LABELS` | Weapon classes to detect | `pistol,knife` |
| `GO2RTC_PORT` | go2rtc WebRTC port | `1984` |

### Frontend (`.env.local`)

| Variable | Description | Default |
|----------|-------------|---------|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API base URL | `http://localhost:8000` |
| `NEXT_PUBLIC_SSE_URL` | SSE alert stream URL | `http://localhost:8000/alerts` |
| `NEXT_PUBLIC_WS_URL` | WebSocket URL | `ws://localhost:8000/ws` |
| `NEXT_PUBLIC_ADMIN_API_KEY` | Admin API key for frontend requests | `sentinel-demo-2026` |

## API Endpoints

### System & Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/system/status` | Combined system status (notifications, decision layer, cameras) |
| GET | `/system/metrics` | Real-time pipeline performance metrics |
| POST | `/decision_layer/reset` | Reset live alert decision layer state |

### Video Streaming

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/video_feed?camera_id=<id>` | MJPEG video stream from specified camera |
| GET | `/api/webrtc/{cam_id}` | Get WebRTC stream metadata for camera |
| POST | `/api/webrtc/{cam_id}/whep` | Proxy WHEP SDP offer to go2rtc |
| PATCH | `/api/webrtc/{cam_id}/whep` | Proxy ICE trickle to go2rtc |
| POST | `/webrtc/offer/{camera_id}` | WebRTC SDP offer/answer exchange |
| GET | `/cameras/status` | Camera status list |

### Alerts & Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/alerts` | SSE event stream (real-time alerts) |
| GET | `/detections` | SSE detection metadata stream (overlay data) |
| POST | `/demo_start/{clip_id}` | Start on-demand analysis of a demo clip |
| DELETE | `/demo_stop/{clip_id}` | Stop on-demand demo clip analysis |
| GET | `/demo_video/{clip_id}` | Serve demo clip video file |

### Incidents & Evidence

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/clips/{alert_id}` | Stream recorded incident clip |
| GET | `/api/clips/list` | List available incident clips |
| GET | `/download_evidence/{alert_id}` | Fetch recorded DVR clip |
| GET | `/download_report/{alert_id}` | Fetch forensic PDF report |
| GET | `/evidence_chain/{alert_id}` | Evidence ledger entry (chain of custody) |

### Detection Categories

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/categories` | Get all available detection categories |
| POST | `/api/analyze` | Analyze a frame or context for a specific category |
| POST | `/api/categories/{category_id}/toggle` | Toggle a detection category on/off |

### Forensic Reports

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/reports/deepseek/status` | DeepSeek report service status |
| POST | `/reports/deepseek/test` | Generate test DeepSeek report (no alert required) |
| POST | `/reports/deepseek/{alert_id}` | Generate DeepSeek report for an alert |
| GET | `/reports/deepseek/{alert_id}` | Fetch cached DeepSeek report |

### Notifications

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/notifications/status` | Notification subsystem status |
| POST | `/notifications/telegram/test` | Send a Telegram test alert |
| POST | `/notifications/telegram/test_video` | Send a Telegram test video alert |

### Face Intelligence

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/face/status` | Face intelligence status |
| GET | `/face/policy` | Get face identity/audit policy |
| POST | `/face/policy` | Update face identity/audit policy |
| POST | `/face/policy/reload` | Reload face policy overrides from disk |
| GET | `/face/registry` | List known people registry |
| GET | `/face/registry/{person_id}` | Get known person profile |
| PUT | `/face/registry/{person_id}` | Create or update known person |
| DELETE | `/face/registry/{person_id}` | Delete known person |
| DELETE | `/face/registry/{person_id}/embeddings` | Clear known person embeddings |
| POST | `/face/registry/{person_id}/enroll` | Enroll known person from image base64 |
| POST | `/face/session/reset` | Reset face unknown-ID session |

### Audio

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/audio/status` | Audio analysis status |
| POST | `/audio/analyze` | Analyze audio clip for distress cues |

### Security & Audit

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/security/status` | Access control status |
| GET | `/audit/status` | Audit log status |
| GET | `/audit/recent` | Recent audit events |

### Controls

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/switch_camera` | Change active camera stream (deprecated) |
| POST | `/set_threshold` | Update model confidence threshold |
| POST | `/set_cooldown` | Update time between consecutive alerts |

## Telegram Alerts

AI-Sentinel can send real-time security alerts to Telegram. This feature enables instant notification of violence, weapon detection, and danger events.

### Setup

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather)
2. Get your chat ID (see [Telegram Alerts Documentation](docs/07_TELEGRAM_ALERTS.md))
3. Configure environment variables in `backend/.env`:
   ```bash
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
   ```

### Documentation

- **[Telegram Alerts Documentation](docs/07_TELEGRAM_ALERTS.md)** - Complete setup and configuration guide
- **[Demo Runbook](docs/04_DEMO_RUNBOOK.md)** - Steps for demonstrating Telegram alerts
- **[Troubleshooting Guide](docs/05_TROUBLESHOOTING.md)** - Common issues and solutions

## Weapon Detection

AI-Sentinel supports two weapon detection backends:

| Backend | Model | Accuracy | Speed | Status |
|---------|-------|----------|-------|--------|
| `yolo` (recommended) | Fine-tuned YOLOv8s | High | ~150 FPS | Active |
| `torchvision_coco` (legacy) | COCO Faster R-CNN | Low | ~15 FPS | Fallback |

See [Weapon Detection Setup Guide](docs/WEAPON_DETECTION_SETUP.md) and [Training Plan](docs/TRAINING_PLAN.md) for training a custom YOLOv8m model with 6 classes.

## Live Alert Decision Layer V2

The V2 temporal decision layer prevents false-positive alerts by requiring temporal confirmation before triggering a visible alert.

- **WATCH_THRESHOLD**: `0.45`
- **CONFIRM_THRESHOLD**: `0.65`
- **CONFIRM_N / CONFIRM_M**: `2 of 3` frames must exceed threshold
- **State machine**: `NORMAL → WATCH → CONFIRMED_VIOLENCE → COOLDOWN`

See [Live Alert Decision Layer V2](docs/02_LIVE_ALERT_DECISION_LAYER_V2.md) for full details.

## Model And GitHub Policy

- Do not train during preservation freeze.
- Do not change model weights during preservation freeze.
- Do not overwrite `backend/best_model.pt`.
- Do not commit model weights to normal GitHub history.
- Do not rely on Git LFS unless it is explicitly approved and configured.
- The current `.gitattributes` documents recommended Git LFS patterns only; it does not enable LFS automatically.

See [Model and Data Policy](docs/06_MODEL_AND_DATA_POLICY.md) for full policy details.

## WebRTC Streaming (Planned)

Phase 1 WebRTC integration will replace MJPEG-over-HTTP streaming with WebRTC via go2rtc for sub-100ms latency. See the [implementation plan](docs/superpowers/plans/2026-05-16-phase1-webrtc-streaming.md) and [design spec](docs/superpowers/specs/2026-05-16-webrtc-streaming-phase1-design.md).

## Agent Framework (.kilo)

The project includes a specialized agent framework in `.kilo/` for project reviews, code quality, and quality gates. See [Agent Workflow Guide](docs/AI_SENTINEL_AGENT_WORKFLOW.md) and [Agent Index](.kilo/AGENTS.md) for details. The system includes:

- **Orchestrator**: Coordinates all review agents
- **Domain specialists**: Inference, face-intel, fusion, VLM, video-capture, evidence, notifications, security
- **Review agents**: Bug hunting, code quality, ML safety, backend API, frontend UX, security/privacy, testing, docs, demo readiness

## Runtime Restore (Colab)

To restore the runtime in Google Colab:

1. Upload the preserved archive to `/content/ai-sentinel`
2. Copy the canonical `best_model.pt` from Google Drive
3. Verify SHA256 matches the documented stable reference
4. Restore decision layer files if lost (`backend/live_alert_decision.py`, `backend/api.py`)
5. Run `notebooks/colab_verify_live_alert_decision_layer.ipynb`

See [Runtime Restore Guide](docs/01_RUNTIME_RESTORE_GUIDE.md) for the full checklist.

## Security

**Important Security Notes:**
- Never commit `.env` file to version control
- Keep Telegram bot token and API keys secret
- Use `.env.example` as template, copy to `.env` and fill in values
- Ensure `config.yml` is in `.gitignore`
- Rotate tokens if accidentally exposed
- The `ADMIN_API_KEY` should be changed before any demo

## Documentation Index

| Doc | Description |
|-----|-------------|
| [Project Status](docs/00_PROJECT_STATUS.md) | Current freeze status and runtime reference |
| [Runtime Restore Guide](docs/01_RUNTIME_RESTORE_GUIDE.md) | Colab runtime restore checklist |
| [Live Alert Decision Layer V2](docs/02_LIVE_ALERT_DECISION_LAYER_V2.md) | Temporal confirmation state machine |
| [Stage 12 External Eval](docs/03_STAGE12_EXTERNAL_EVAL.md) | External dataset evaluation results |
| [Demo Runbook](docs/04_DEMO_RUNBOOK.md) | Pre-demo checklist and run procedures |
| [Troubleshooting](docs/05_TROUBLESHOOTING.md) | Common issues and solutions |
| [Model and Data Policy](docs/06_MODEL_AND_DATA_POLICY.md) | Preservation and backup policies |
| [Telegram Alerts Setup](docs/07_TELEGRAM_ALERTS.md) | Complete Telegram configuration guide |
| [API Reference](docs/API_REFERENCE.md) | Complete endpoint documentation (50+ endpoints) |
| [Environment Variables](docs/ENV_VARS.md) | Master env var table (backend + frontend) |
| [Frontend Components](docs/FRONTEND_COMPONENTS.md) | Component catalog, hooks, data flow |
| [Cloud Deployment](docs/CLOUD_DEPLOYMENT.md) | AWS GPU instance deployment |
| [Weapon Detection Setup](docs/WEAPON_DETECTION_SETUP.md) | YOLO weapon detection configuration |
| [Training Plan](docs/TRAINING_PLAN.md) | Weapon detection model training |
| [Colab Training](docs/colab-training.md) | Zero-touch Colab training guide |
| [Agent Workflow Guide](docs/AI_SENTINEL_AGENT_WORKFLOW.md) | Agent framework usage |
| [Video Performance Overhaul](docs/VIDEO_PERFORMANCE_OVERHAUL_DESIGN.md) | Performance optimization designs |
| [Changelog](CHANGELOG.md) | Full project history timeline |
| [Project Overview](PROJECT_DOCUMENTATION.md) | High-level architecture and feature overview |
| [WebRTC Streaming Plan](docs/superpowers/plans/2026-05-16-phase1-webrtc-streaming.md) | Low-latency streaming implementation |
| [Deployment Plan](docs/superpowers/plans/2026-04-17-tasi-ai-engine-v11-production-deployment.md) | Production deployment roadmap |
| [Benchmarks](docs/benchmarks/threat_latency_benchmark.md) | Threat latency benchmarks |
| [Arabic Docs](telegram_setup_guide_ar.md) | Arabic-language Telegram setup guide |

## License

[Add your license information here]
