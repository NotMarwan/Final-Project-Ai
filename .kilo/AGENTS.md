# Kilo Agents — AI Sentinel Project

**Active source:** `.kilo/kilo.jsonc` (JSON/JSONC agent definitions with full prompts, permissions, and models).  
**Backup documentation:** `.kilo/agent/*.md` (human-readable handbooks for reference only).

This directory contains specialized subagent definitions for the AI Sentinel project, including **domain specialists** and the **AI-Sentinel Review Agent System**.

## Agent Index

### Domain Specialists (runtime expertise)

| Agent | Expertise | Key Files |
|-------|-----------|-----------|
| `inference-agent` | Violence detection model (X3D-M / SlowFast), preprocessing, thresholds | `backend/inference.py`, `backend/api.py:capture_loop` |
| `face-intel-agent` | Face recognition, registry CRUD, identity masking, audit events | `backend/face_intel.py`, `/face/*` endpoints |
| `fusion-agent` | Multi-modal threat fusion (violence + motion + weapon weights), severity calculation | `backend/fusion.py`, `ThreatFusionEngine.assess()` |
| `vlm-agent` | Groq VLM report generation, asynchronous forensic narrative | `_call_vlm_forensics()` in `backend/api.py`, `/get_report/*` |
| `video-capture-agent` | Multi-source camera capture, RTSP/USB/file, ring buffer, MJPEG/SSE streaming | `capture_loop()`, `_open_capture()`, `_drain_to_latest()` |
| `audio-agent` | Scream/distress detection, loudness analysis (currently disabled) | `backend/audio.py`, `/audio/*` endpoints |
| `evidence-agent` | Evidence DVR, PDF reporting & chain-of-custody specialist — clips, thumbnails, ledger, Arabic-ready PDFs | `backend/evidence.py`, `backend/reporting.py`, `_write_evidence_clip()` |
| `api-endpoints-agent` | FastAPI routes, streaming responses, validation, authz, lifespan | Entire `backend/api.py` route table |
| `frontend-agent` | Next.js dashboard components, SSE alerts, MJPEG video, state management | `app/page.tsx`, `components/*`, Tailwind layout |
| `notifications-agent` | Telegram bot alerts, queue/retry, status monitoring | `backend/notifications.py`, `/notifications/*` |
| `security-audit-agent` | API key auth, role-based access, audit log (JSONL) | `backend/security.py`, `/security/*`, `/audit/*` |

### Review & Orchestration Agents (project quality)

| Agent | Role | Purpose | Mode |
|-------|------|---------|------|
| `ai-sentinel-orchestrator` | **Primary** — Project Commander | Coordinates all review agents, merges findings, produces final roadmap | primary |
| `ai-sentinel-graduation-judge` | Graduation Evaluator | Scores project as university capstone, defense Q&A | subagent |
| `ai-sentinel-company-adoption-reviewer` | Business Adoption Reviewer | Evaluates business fitness, buyer personas, objections | subagent |
| `ai-sentinel-full-project-reviewer` | Full-System Auditor | End-to-end audit of code, docs, config, runtime assumptions | subagent |
| `ai-sentinel-bug-hunter` | QA Bug Hunter | Finds crashes, fragility, edge cases, `confirmed_alert` violations | subagent |
| `ai-sentinel-code-quality-reviewer` | Code Quality Advisor | Refactoring opportunities, naming, duplication, separation | subagent |
| `ai-sentinel-ml-decision-layer-reviewer` | ML Safety Specialist | Verifies V2 correctness, SHA consistency, thresholds, temporal confirmation | subagent |
| `ai-sentinel-backend-api-reviewer` | Backend API Reviewer | Endpoint correctness, auth, reliability, Telegram, video streaming | subagent |
| `ai-sentinel-frontend-ux-reviewer` | Frontend UX Reviewer | Dashboard clarity, operator workflow, visual polish, demo readiness | subagent |
| `ai-sentinel-security-privacy-ethics-reviewer` | Security & Ethics Officer | Responsible AI, privacy, legal compliance, human-in-the-loop | subagent |
| `ai-sentinel-testing-qa-verification` | Testing Lead | Proposes test suite, demo smoke checklist, verification tests | subagent |
| `ai-sentinel-docs-presentation-reviewer` | Documentation Specialist | README polish, defense talking points, demo script, FAQ | subagent |
| `ai-sentinel-product-vision-agent` | Product Vision Strategist | Roadmap beyond graduation, innovative features, business model | subagent |
| `ai-sentinel-demo-readiness-agent` | Demo Engineer | Go/No-Go checklist, commands, backup plan, exact script | subagent |
| `ai-sentinel-final-integration-reviewer` | Final Auditor | Merges all reports into maturity scores and integrated roadmap | subagent |

## Configuration

Agent loading is governed by:
- `kilo.json` — `agents[]` array (name, description, enabled) provides the agent index
- `.kilo/kilo.jsonc` — **authoritative** agent definitions with full `mode`, `prompt`, `permission`, `model`, `temperature`, and `steps` fields

The **ai-sentinel-orchestrator** is set as a `primary` agent and can delegate to all review subagents.

## Usage

When Kilo needs to answer a project-level question, it routes to the appropriate agent. You can manually select an agent from the status bar or invoke by name in your query.

To start a full project review:

1. Select `ai-sentinel-orchestrator` as active agent
2. Send: *"Use the AI-Sentinel agent system. Act as ai-sentinel-orchestrator. First inspect the repository, then delegate to all review agents and merge their findings into one final P0/P1/P2/P3 roadmap. Protect best_model.pt, secrets, and the confirmed_alert safety rule."*

The orchestrator will delegate to each specialist and produce a consolidated report with scores, risks, and a prioritized action plan.

## Safety Rules

All review agents respect these immutable constraints:
- Do not modify `backend/best_model.pt` or any model weights
- Do not weaken `confirmed_alert` as the visible alert control
- Do not train or retrain during preservation freeze
- Do not expose secrets (Telegram tokens, Groq keys, .env)
- Do not make risky production changes without explicit user approval

## Adding New Agents

1. Create a `.md` file in `.kilo/agent/` with YAML frontmatter and prompt body
2. Add entry to `kilo.json` `agents` array
3. Add entry to `.kilo/kilo.jsonc` `agent` object with full definition
4. Restart Kilo session or reload config

---

**Last updated:** 2026-05-12 — AI Sentinel Project — Kilo Subagents
The active configuration is JSON/JSONC-based; Markdown files are backup only.
