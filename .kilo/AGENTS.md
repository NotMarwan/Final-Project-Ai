# Kilo Agents — AI Sentinel Project

This directory contains specialized subagent definitions for the AI Sentinel project. Each `.md` file documents a domain-specific agent with:

- **Scope** — what the agent is responsible for
- **Technical Context** — which source files and functions to consult
- **Responsibilities** — operational duties
- **Configuration Knobs** — env vars, config.yml settings
- **Integration Points** — API endpoints, state hooks, other modules
- **Edge Cases & Gotchas** — common pitfalls and tuning notes
- **Example Queries** — what questions this agent can answer

## Agent Index

| Agent | Expertise | Key Files |
|-------|-----------|-----------|
| `inference-agent.md` | Violence detection model (X3D-M / SlowFast), preprocessing, thresholds | `backend/inference.py`, `backend/api.py:capture_loop` |
| `face-intel-agent.md` | Face recognition, registry CRUD, identity masking, audit events | `backend/face_intel.py`, `/face/*` endpoints |
| `fusion-agent.md` | Multi-modal threat fusion (violence + motion + weapon weights), severity calculation | `backend/fusion.py`, `ThreatFusionEngine.assess()` |
| `vlm-agent.md` | Groq VLM report generation, asynchronous forensic narrative | `_call_vlm_forensics()` in `backend/api.py`, `/get_report/*` |
| `video-capture-agent.md` | Multi-source camera capture, RTSP/USB/file, ring buffer, MJPEG/SSE streaming | `capture_loop()`, `_open_capture()`, `_drain_to_latest()` |
| `audio-agent.md` | Scream/distress detection, loudness analysis (currently disabled) | `backend/audio.py`, `/audio/*` endpoints |
| `evidence-agent.md` | DVR clip compilation, snapshots, PDF reports, evidence ledger (JSONL) | `backend/evidence.py`, `backend/reporting.py`, `_write_evidence_clip()` |
| `api-endpoints-agent.md` | FastAPI routes, streaming responses, validation, authz, lifespan | Entire `backend/api.py` route table |
| `frontend-agent.md` | Next.js dashboard components, SSE alerts, MJPEG video, state management | `app/page.tsx`, `components/*`, Tailwind layout |
| `notifications-agent.md` | Telegram bot alerts, queue/retry, status monitoring | `backend/notifications.py`, `/notifications/*` |
| `security-audit-agent.md` | API key auth, role-based access, audit log (JSONL) | `backend/security.py`, `/security/*`, `/audit/*` |

## Usage

When Kilo needs to answer a question or perform a task in this project, it will automatically route to the appropriate subagent based on the domain. The agents are **permanently installed** in the `.kilo/agent/` directory.

To manually consult an agent, read its `.md` file directly or ask Kilo questions scoped to that domain (e.g., "face-intel: why are known faces not being recognized?" triggers the Face Intel agent's context).

## Configuration

Agent loading governed by:
- `kilo.json` — `agents[]` array, one entry per agent file (name + description)
- Enabled/disabled per-agent via `"enabled": true/false`

## Adding New Agents

1. Create a new `.md` file in `.kilo/agent/` following the structure above
2. Register it in `kilo.json` `agents` array
3. Restart Kilo session (or reload config)

---
**Created:** 2026-05-12 — AI Sentinel Project — Kilo Subagents