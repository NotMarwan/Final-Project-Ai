# Project: AI Sentinel

## Current Status
**Preservation Freeze** since 2026-05-07 — Stable runtime documented and preserved. Demo-ready with Live Alert Decision Layer V2.

## Features Implemented
- [Done] X3D spatiotemporal violence detection (32-frame rolling window, ~96% accuracy)
- [Done] FastAPI backend with 50+ REST/SSE endpoints
- [Done] Next.js 16 dashboard with 6 tabs (monitor, demo-clips, incidents, intelligence, operations, system)
- [Done] Live Alert Decision Layer V2 (temporal confirmation, state machine)
- [Done] Telegram alerts with severity filtering and rate limiting
- [Done] Weapon detection (YOLOv8s, 6 classes, ~150 FPS)
- [Done] Face intelligence (known registry, identity labeling, audit trail)
- [Done] Multi-modal threat fusion (violence + motion + weapon + intrusion)
- [Done] Categorized detection system (violence, weapon, firearms, threat, panic, danger, intrusion)
- [Done] Groq VLM forensic reports (Arabic/English)
- [Done] DeepSeek/OpenRouter AI report integration
- [Done] Evidence clip recording, thumbnail generation, PDF reporting
- [Done] GPU auto-detection (CUDA/MPS/CPU)
- [Done] Decoupled capture/inference pipeline
- [Done] Multi-dataset training pipeline (RWF-2000, UFC, etc.)
- [Done] Security/audit system (API key auth, JSONL audit logs)
- [Done] WebRTC streaming architecture (Phase 1 implemented)
- [Done] Canvas overlay for detection bounding boxes
- [Done] Docker deployment with GPU passthrough

## Pending / In Progress
- [In-Progress] VIGI VMS camera integration and real camera feed testing
- [Pending] Full production WebRTC rollout (Phase 2: multi-camera, adaptive bitrate)
- [Pending] Weapon detection model upgrade (YOLOv8m with 10k+ dataset)
- [Pending] Video visual overlays enhancement
- [Pending] Live monitor source switcher UI
- [Pending] End-to-end demo preparation and verification
- [Pending] Arabic documentation completeness check

## Technical Notes
- Backend API base URL: `http://localhost:8002` (configured via `NEXT_PUBLIC_API_BASE_URL`)
- SSE alert stream: `http://localhost:8002/alerts`
- Stable runtime model SHA256: `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`
- Local model SHA256: `1fb38eeb54821d827a4621ac3fce4ad98488bc05fbf99df9ab78a13ed223b6cb` (mismatch — verify before demo)
- Safety rule: `confirmed_alert` controls visible alert, not `model_prediction`
- Docker: `docker-compose up -d --build` for GPU-enabled deployment
- Frontend lint: `npm run lint` (ESLint on components/app/lib/hooks)
- Typecheck: `npm run typecheck` (tsc --noEmit)
- Face policy tests: `npm run test:face-policy`

## Context Logs
- 2026-05-16: Phase 1 WebRTC streaming implemented (go2rtc bridge, WHEP proxy, WebRTC player)
- 2026-05-16: Canvas overlay and useDetectionStream hook added
- 2026-05-07: Preservation freeze — all docs, manifests, runtime state documented
- 2026-05-05: Weapon detection training pipeline and evaluation
- 2026-05-02: Multi-angle recording protocol and threat latency benchmarks
- 2026-04-28: Detection categories expansion (7 categories)
- 2026-04-25: Multi-dataset training, performance optimization (2s → 500ms)
- 2026-04-20: Face intelligence system and policy controls
- 2026-04-17: Groq VLM forensic reports, Telegram finalization
- 2026-04-10: Initial AI Sentinel Core
