# AI Sentinel - Project Overview

An AI-powered real-time security surveillance system designed for violence detection, weapon detection, face intelligence, and automated incident reporting.

## Architecture

```
Cameras / RTSP / Files
        │
        ▼
┌───────────────────┐
│  capture_loop()    │  ← Frame capture (decoupled from inference)
│  _open_capture()   │     MJPEG, RTSP, USB, file sources
│  _drain_to_latest()│
└────────┬──────────┘
         │ frames
         ▼
┌───────────────────┐
│  Inference Engine  │  ← X3D spatiotemporal (32-frame rolling window)
│  (inference.py)    │     Weapon detection (YOLOv8)
│  (weapon.py)       │     Face recognition (FaceIntelEngine)
│  (face_intel.py)   │     Audio analysis (AudioRiskAnalyzer)
│  (audio.py)        │
└────────┬──────────┘
         │ predictions
         ▼
┌───────────────────┐
│  Threat Fusion     │  ← Multi-modal fusion (violence + motion + weapon)
│  (fusion.py)       │     Categorized detection system
│  (detection_categories.py)│
└────────┬──────────┘
         │ threat scores
         ▼
┌───────────────────┐
│ Decision Layer V2  │  ← Temporal confirmation (WATCH/CONFIRMED/COOLDOWN)
│ (live_alert_decision.py)│ Prevents false positives
└────────┬──────────┘
         │ confirmed_alert
         ▼
┌───────────────────┐     ┌──────────────────┐
│  Notifications     │────►│ Telegram Bot      │
│  (notifications.py)│     └──────────────────┘
│  Evidence DVR      │────►│ Evidence clips    │
│  (evidence.py)     │     └──────────────────┘
│  Forensic Reports  │────►│ Groq VLM /        │
│  (reporting.py)    │     │ DeepSeek Reports  │
└────────┬──────────┘     └──────────────────┘
         │ SSE events
         ▼
┌───────────────────┐
│  Dashboard (Next.js)│  ← Live Monitor, Incidents, Intelligence,
│  (app/page.tsx)    │     Operations, Demo Clips, System tabs
└───────────────────┘
```

## Tech Stack

### Frontend (Next.js & Tailwind)

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 16 (App Router), React 19 |
| Styling | Tailwind CSS, `shadcn/ui` components |
| Streaming | MJPEG-over-HTTP, WebRTC (via go2rtc, planned) |
| Real-time | Server-Sent Events (SSE) for alerts and detections |
| Icons | Lucide React |
| State | React hooks (`useState`, `useRef`, `useCallback`, custom hooks) |

### Backend (Python & FastAPI)

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI with `asyncio` |
| AI Model | X3D spatiotemporal (32-frame rolling window, ~96% accuracy) |
| Weapon Detection | YOLOv8s (fine-tuned), COCO Faster R-CNN (legacy fallback) |
| Face Intelligence | Face recognition with known registry, IoU tracking, anti-flicker |
| Threat Fusion | Multi-modal (violence + motion + weapon + intrusion) |
| Forensic Reports | Groq VLM (Llama 4 Scout) + DeepSeek/OpenRouter |
| Notifications | Telegram Bot API |
| Streaming | MJPEG-over-HTTP, WebRTC WHEP (go2rtc sidecar) |
| Evidence | DVR clip recording, thumbnails, PDF reports, chain-of-custody ledger |

### Mobile & Desktop

| Platform | Technology |
|----------|-----------|
| Android | Capacitor 8 |
| Desktop | Electron |

## Features

### Detection & Analysis
- **Violence Detection**: X3D spatiotemporal inference (32-frame rolling window)
- **Weapon Detection**: YOLOv8 with 6 classes (pistol, rifle, shotgun, knife, sword, revolver)
- **Face Intelligence**: Known person registry, identity labeling, anti-flicker stabilization, audit logging
- **Audio Analysis**: Scream/distress detection (configurable)
- **Detection Categories**: Multi-category system (violence, weapon, firearms, threat, panic, danger, intrusion)
- **Person Detection**: Person detector with centroid tracking
- **Visual Annotation**: Real-time bounding box and label overlay on video feed

### Alert & Decision Systems
- **Live Alert Decision Layer V2**: Temporal confirmation state machine (WATCH/CONFIRMED/COOLDOWN)
- **Multi-modal Threat Fusion**: Combines violence, motion, weapon scores into unified severity
- **Telegram Notifications**: Real-time alerts with severity filtering and rate limiting
- **Alert Cooldown**: Prevents alert flooding with configurable minimum intervals

### Incident & Evidence Management
- **Automatic Clip Recording**: DVR-style evidence capture on confirmed alerts
- **Thumbnail Generation**: Visual snapshots for each incident
- **Evidence Ledger**: Chain-of-custody tracking for all recorded evidence
- **PDF Reports**: Automated Arabic/English incident reports with forensic analysis

### Forensic Reporting
- **Groq VLM Reports**: AI-generated incident descriptions, confidence analysis, behavioral interpretation
- **DeepSeek/OpenRouter Reports**: Alternative AI report provider with status and caching
- **Downloadable PDFs**: Formatted reports ready for presentation/defense

### Frontend Dashboard
- **Live Monitor**: Real-time video feed with overlay annotations (boxes, labels, HUD)
- **Incident Feed**: Real-time alert sidebar with category filtering
- **Incident Panel**: Detailed incident view with evidence, reports, face policy controls
- **Geo Dashboard**: Operations map with camera locations
- **Clip Player**: Video clip replay with loop, speed control
- **Incident Replay**: Side-panel replay for demo clips
- **WebRTC Player**: Low-latency browser video (planned for full production)
- **Canvas Overlay**: Detection bounding boxes drawn on canvas over video

### Performance & Optimization
- **GPU Auto-detection**: Automatic CUDA/MPS/CPU selection
- **Decoupled Capture/Inference**: Frame capture runs independently of AI inference
- **Configurable JPEG Quality**: Trade-off between stream quality and bandwidth
- **Fast Annotation Mode**: Optimized visual annotation path
- **Configurable Stride**: Frame sampling rate for inference

## Documentation

| Category | Docs |
|----------|------|
| **Status & Reference** | [Project Status](docs/00_PROJECT_STATUS.md), [Runtime Restore Guide](docs/01_RUNTIME_RESTORE_GUIDE.md) |
| **Decision Layer** | [Live Alert Decision Layer V2](docs/02_LIVE_ALERT_DECISION_LAYER_V2.md) |
| **Evaluation** | [Stage 12 External Eval](docs/03_STAGE12_EXTERNAL_EVAL.md), [Verification Report](docs/VERIFICATION_REPORT.md) |
| **Demo & Operations** | [Demo Runbook](docs/04_DEMO_RUNBOOK.md), [Troubleshooting](docs/05_TROUBLESHOOTING.md) |
| **Policies** | [Model and Data Policy](docs/06_MODEL_AND_DATA_POLICY.md) |
| **Telegram** | [Telegram Alerts](docs/07_TELEGRAM_ALERTS.md), [Arabic Guide](telegram_setup_guide_ar.md) |
| **Deployment** | [Cloud Deployment](docs/CLOUD_DEPLOYMENT.md) |
| **Weapon Detection** | [Setup Guide](docs/WEAPON_DETECTION_SETUP.md), [Training Plan](docs/TRAINING_PLAN.md) |
| **Colab** | [Training Guide](docs/colab-training.md), [Zero-Touch Plan](docs/colab-zero-touch-plan.md) |
| **Agent System** | [Agent Workflow Guide](docs/AI_SENTINEL_AGENT_WORKFLOW.md) |
| **Performance** | [Video Overhaul Design](docs/VIDEO_PERFORMANCE_OVERHAUL_DESIGN.md), [Plan](docs/VIDEO_PERFORMANCE_OVERHAUL_PLAN.md) |
| **Upcoming** | [WebRTC Streaming Plan](docs/superpowers/plans/2026-05-16-phase1-webrtc-streaming.md), [Weapon Upgrade Spec](docs/superpowers/specs/2026-05-15-weapon-detection-upgrade-design.md) |
| **Benchmarks** | [Threat Latency](docs/benchmarks/threat_latency_benchmark.md), [Recording Protocol](docs/benchmarks/multi_angle_recording_protocol.md) |

## Project Structure

- **`app/`**: Core Next.js application layout and pages
  - `layout.tsx`: Root layout, font loading, PWA manifest, metadata
  - `page.tsx`: Main dashboard with 6 tabs (monitor, demo-clips, incidents, intelligence, operations, system)
  - `globals.css`: Global styles with CSS custom properties
  - `manifest.ts`: PWA manifest configuration
- **`components/`**: Reusable React components
  - `video-player.tsx`: Main video player with MJPEG/WebRTC, overlays, HUD
  - `webrtc-player.tsx`: WebRTC video player with ICE/STUN
  - `canvas-overlay.tsx`: Detection bounding box overlay canvas
  - `alert-feed.tsx`: Real-time incident alert sidebar with category filtering
  - `incident-panel.tsx`: Detailed incident view with evidence, reports, PDF export
  - `ai-report.tsx`: AI-generated forensic report display (Groq/DeepSeek)
  - `dashboard-header.tsx`: Main navigation header with SSE status, privacy toggle, face policy badge
  - `clip-player.tsx`: Evidence clip video player with loop/speed controls
  - `clip-sidebar.tsx`: Clip list sidebar with demo clip replay
  - `incident-replay.tsx`: Full incident replay component with auto-play
  - `category-filter.tsx`: Detection category filter toggle group
  - `telegram-status.tsx`: Telegram notification status card
  - `geo-dashboard.tsx`: Operations map with geo-intelligence deck
  - `theme-provider.tsx`: Theme provider wrapper
  - `ui/`: Base UI components (button, card, dialog, badge, slider, switch, tabs, etc.)
- **`hooks/`**: Custom React hooks
  - `use-detection-stream.ts`: SSE connection management for detection overlay data
  - `use-clip-playback.ts`: Video clip playback controls (play, pause, loop, speed)
  - `use-toast.ts`, `use-mobile.ts`: Utility hooks
- **`lib/`**: Shared utilities
  - `detection-types.ts`: Type definitions for detection categories, scores, capabilities
  - `dashboard-data.ts`: Mock/shared dashboard data
  - `utils.ts`: Tailwind CSS class merger (`cn()` helper)
- **`backend/`**: Python FastAPI server
  - `api.py`: Main FastAPI application (2543 lines, 50+ endpoints)
  - `inference.py`: X3D violence detection inference pipeline with configurable stride
  - `weapon.py`: Weapon detection engine with YOLO backend
  - `fusion.py`: Multi-modal threat fusion engine
  - `face_intel.py`: Face recognition, registry, and intelligence engine
  - `live_alert_decision.py`: Temporal alert confirmation state machine
  - `notifications.py`: Telegram notification service with rate limiting
  - `reporting.py`: PDF incident report generator
  - `evidence.py`: Evidence clip recording and management
  - `security.py`: Access control and JSONL audit logging
  - `audio.py`: Audio risk analyzer (scream/distress detection)
  - `detection_categories.py`: Multi-category detection system
  - `go2rtc_bridge.py`: go2rtc sidecar process management
  - `calibration_utils.py`: Model calibration profile loading
  - `config.yml`: Centralized YAML configuration
  - `camera_profiles.yml`: Camera source definitions
- **`scripts/`**: Utility scripts (setup, testing, training)
- **`notebooks/`**: Jupyter/Colab notebooks
- **`docs/`**: Project documentation
- **`desktop/`**: Electron desktop wrapper
- **`android/`**: Capacitor Android app

## Key Safety Rules

1. **`confirmed_alert` controls the visible red alert**, never `model_prediction`
2. **Preservation freeze in effect** — do not train or modify model weights
3. **Local `best_model.pt` SHA mismatch** — verify before demo
4. **Keep tokens and secrets out of git** — use `.env` files
5. **Decision Layer V2** must remain enabled for safe demo operation
