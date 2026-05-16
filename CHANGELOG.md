# Changelog

## 2026-05-16 — WebRTC Streaming + Performance Phase 1

- Implemented WebRTC streaming architecture with go2rtc sidecar (bridge, config, frontend player)
- Added Canvas overlay and `useDetectionStream` hook for real-time detection bounding boxes
- Added `/api/webrtc/{cam_id}`, `/detections` SSE endpoint, and raw mode for video stream
- Instrumented pipeline metrics, persistent WebRTC connections, weapon detection cache
- Added Docker support with GPU passthrough (`docker-compose.yml`, `Dockerfile`)
- Added cloud deployment guide for AWS GPU instances (g4dn.xlarge)
- Added auto-detect GPU, configurable JPEG quality, and fast annotation mode
- Decoupled frame capture from AI inference (no destructive frame skip)
- Added GPU auto-detection and ONNX export support

## 2026-05-07 — Stable Live Alert V2 Freeze

- Froze the current AI-Sentinel preservation layout for local backup and GitHub preparation
- Documented the stable live alert decision-layer V2 behavior and demo safety rules
- Added restore guide, troubleshooting, model-policy, and Stage 12 external evaluation docs
- Added preservation manifests and backup/archive structure
- Updated Git hygiene files to exclude large local-only artifacts from standard GitHub upload
- Recorded critical warning: workspace-local `backend/best_model.pt` SHA mismatch
- Added Telegram alert delivery hardening and testing endpoints
- Added structured weapon detection overlays

## 2026-05-05 — Weapon Detection Training & Integration

- Added Colab fine-tuning plan and notebook for SlowFast model
- Added RWF-2000 manifest builder and baseline evaluation tools
- Updated weapon detection engine with structured overlay rendering
- Added backpressure and runtime safety policy for weapon detection
- Added weapon warmup status and runtime latency metrics
- Added weapon runtime smoke validation tests

## 2026-05-02 — Multi-Angle Recording & Threat Latency Benchmarks

- Added multi-angle recording benchmark protocol and checklist
- Added threat latency benchmark harness
- Optimized stride, decoupled weapon alerts, premium incident replay UX
- Harden decoupled alerts and incident replay verification
- Implemented honest zone contract and intrusion detection context

## 2026-04-28 — Detection Categories Expansion

- Added categorized detection system (beyond violence: weapon, firearms, threat, panic, danger, intrusion)
- Added multi-dataset training pipeline and augmentation
- Added clip viewing sidebar with Twitch-style loop playback
- Added frontend lint and typecheck gates
- Stabilized core backend APIs and strict frontend types
- Enhanced navigation with category filtering

## 2026-04-25 — Multi-Dataset Training & Performance Optimization

- Implemented multi-dataset training pipeline (RWF-2000, UFC, etc.)
- Added multi-angle X3D model for improved 170cm eye-level detection
- Optimized inference pipeline: reduced latency from ~2s to <500ms
- Integrated all detection categories and optimization settings

## 2026-04-20 — Face Intelligence & Policy System

- Implemented phase-1 face intelligence skeleton (detection, tracking, enrollment)
- Added known registry management and enrollment APIs
- Stabilized unknown IDs with IoU tracking and anti-flicker
- Face event metadata enrichment and report timeline details
- Face policy toggles: identity labeling, recognition audit, known anti-flicker
- Face policy persistence across restarts, runtime reload endpoint
- Policy sync health badge in dashboard header with one-click jump to controls
- Face policy updated timestamp and diagnostics tooltip

## 2026-04-17 — Groq VLM Forensic Reports

- Migrated forensic engine to Groq (Llama 4 Scout)
- Enabled English-only reporting with auto-refresh on new detection
- Configured Telegram notifications and finalized project launch setup
- Production deployment plan

## 2026-04-10 — Initial AI Sentinel Core

- Initial commit: AI Sentinel Core
- Full project source with Next.js frontend and FastAPI backend
- X3D violence detection inference engine
- Real-time MJPEG streaming from cameras
- Basic alert system with SSE
- Evidence capture and thumbnail generation
- Dashboard with live monitor tab
