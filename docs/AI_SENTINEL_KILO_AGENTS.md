# AI-Sentinel Kilo Agent System

## Overview

This project contains a comprehensive multi-agent review system for evaluating and improving AI-Sentinel. The agents are defined in JSON/JSONC format in `.kilo/kilo.jsonc`, which is the **active source of truth**. The Markdown files under `.kilo/agent/` are maintained as human-readable backups only and are not used directly by Kilo at runtime.

**Active config:** `.kilo/kilo.jsonc` (detailed agent definitions) with `kilo.json` providing the agent index.  
**Backup files:** `.kilo/agent/*.md` (human-readable handbooks).  
**No `.kilo/agents/` directory** — all agent definitions are in `.kilo/agent/` and the JSONC config.

## Agent Categories

### Domain Specialists (pre-existing)
These 11 agents handle domain-specific questions about the running system:

| Agent | Expertise |
|-------|-----------|
| `inference-agent` | Violence detection model (X3D-M), preprocessing, thresholds |
| `face-intel-agent` | Face recognition, registry CRUD, identity masking |
| `fusion-agent` | Threat fusion scoring (violence+motion+weapon) |
| `vlm-agent` | Groq VLM forensic report generation |
| `video-capture-agent` | Camera capture, RTSP/USB/file, ring buffer, MJPEG/SSE |
| `audio-agent` | Scream/distress detection (disabled) |
| `evidence-agent` | Evidence DVR, PDF reports, chain-of-custody |
| `api-endpoints-agent` | FastAPI routes, validation, authz, streaming |
| `frontend-agent` | Next.js dashboard, SSE alerts, MJPEG video |
| `notifications-agent` | Telegram bot alerts, queue/retry |
| `security-audit-agent` | API key auth, RBAC, audit logging |

### Review & Orchestration Agents (new)

| Agent | Role | Mode |
|-------|------|------|
| `ai-sentinel-orchestrator` | Primary project commander — coordinates all review agents, merges findings, produces final roadmap | **primary** |
| `ai-sentinel-graduation-judge` | Evaluates project as a university graduation committee member | subagent |
| `ai-sentinel-company-adoption-reviewer` | Evaluates business adoption fitness for real organizations | subagent |
| `ai-sentinel-full-project-reviewer` | End-to-end system audit across all files | subagent |
| `ai-sentinel-bug-hunter` | Finds bugs, crashes, fragility, confirmed_alert violations | subagent |
| `ai-sentinel-code-quality-reviewer` | Proposes refactoring while preserving behavior | subagent |
| `ai-sentinel-ml-decision-layer-reviewer` | Verifies V2 correctness, SHA consistency, ML safety | subagent |
| `ai-sentinel-backend-api-reviewer` | Reviews every endpoint for correctness, auth, reliability | subagent |
| `ai-sentinel-frontend-ux-reviewer` | Reviews dashboard clarity, polish, operator workflow | subagent |
| `ai-sentinel-security-privacy-ethics-reviewer` | Reviews responsible AI, privacy, legal compliance | subagent |
| `ai-sentinel-testing-qa-verification` | Proposes test suite and demo verification checklist | subagent |
| `ai-sentinel-docs-presentation-reviewer` | Upgrades README, docs, defense talking points, demo script | subagent |
| `ai-sentinel-product-vision-agent` | Creates visionary product roadmap and business model ideas | subagent |
| `ai-sentinel-demo-readiness-agent` | Produces Go/No-Go verdict with exact commands and backup plan | subagent |
| `ai-sentinel-final-integration-reviewer` | Merges all reports into final maturity scores | subagent |

## How to Use

### Starting a Review Session

1. Open any file or the chat in Kilo Code.
2. Set the active agent to **ai-sentinel-orchestrator** (use the agent selector in the status bar or command palette).
3. Send the following message to begin:

```
Use the AI-Sentinel agent system. Act as ai-sentinel-orchestrator. First inspect the repository, then delegate to the graduation judge, company adoption reviewer, bug hunter, ML decision layer reviewer, backend reviewer, frontend reviewer, security/privacy reviewer, QA verifier, demo readiness agent, and product vision agent. Merge their findings into one final P0/P1/P2/P3 roadmap. Do not modify source code yet. Documentation and Kilo agent configuration edits are allowed. Protect best_model.pt, secrets, and the confirmed_alert safety rule.
```

The orchestrator will automatically delegate to each subagent in priority order and produce a consolidated report.

### Manual Invocation

You can also manually consult a specific subagent by using its name:

- Type `@graduation-judge` — but the exact alias is the agent name like `ai-sentinel-graduation-judge` (check agent list in Kilo).
- Or include in your message: "Use ai-sentinel-ml-decision-layer-reviewer to verify V2 safety."

## Permissions & Safety

**Critical safety rules enforced by all agents:**
- `confirmed_alert` / `confirmedAlert` is the only source for visible red alert; `model_prediction` is telemetry only
- Live Alert Decision Layer V2 must not be weakened
- `VIOLENCE_CLS = 1` must be respected
- **Preservation Freeze**: No training, no model weight changes, no overwriting best_model.pt
- No secrets exposed (Telegram tokens, Groq keys, .env)
- No risky source code changes without explicit user approval

**Permission levels:**
- Orchestrator: can edit docs and Kilo config; must ask before source code edits
- Review agents (most): read-only (edit: deny, bash: read-only commands)
- Testing agent: may propose creating test files (edit: ask)
- Docs presenter: may edit docs (edit: ask)

See each agent's markdown file in `.kilo/agent/` for full permission matrix.

## Agent File Locations

- Primary orchestrator: `.kilo/agent/ai-sentinel-orchestrator.md`
- Review agents: `.kilo/agent/ai-sentinel-*.md`
- Domain specialists: `.kilo/agent/{inference,face-intel,fusion,vlm,video-capture,audio,evidence,api-endpoints,frontend,notifications,security-audit}-agent.md`

## Configuration Files

- `kilo.json` — agent registry (simple name + description array)
- `.kilo/kilo.jsonc` — detailed agent definitions (mode, prompt, permissions)
- `.kilo/AGENTS.md` — human-readable index and usage guide

## Recommended Workflow

1. **Start orchestrator** with the recommended first message (above)
2. Wait for it to delegate and collect reports
3. Orchestrator produces final integrated roadmap with P0/P1/P2/P3 priorities
4. Review the roadmap; approve safe changes
5. Orchestrator proposes specific documentation updates or test scaffolding
6. Implement approved changes incrementally
7. Re-run orchestrator after changes to verify improvement

## Output Artifacts

When the orchestrator finishes, you will receive:

- Executive summary
- Scores card (graduation readiness, adoption, demo safety, code quality, security)
- Top 10 critical risks
- Top 10 recommended improvements
- P0/P1/P2/P3 prioritized action lists
- Demo Go/No-Go verdict
- Files changed and files recommended
- Residual risks

## Safety & Ethics Reminder

AI-Sentinel involves surveillance, violence detection, and optional face recognition. All reviews must consider:
- Privacy by design
- Human-in-the-loop (no autonomous action)
- False accusation mitigation
- Data retention policies
- Access control and audit
- Legal compliance (GDPR, CCPA, workplace laws)

Any proposal that weakens these is rejected as a policy violation.

## Troubleshooting

**Agents not appearing in Kilo?**
- Reload VS Code window (Ctrl+Shift+P → "Reload Window")
- Check `.kilo/kilo.jsonc` syntax (valid JSONC)
- Ensure `"enabled": true` in `kilo.json` entries

**Permission denied errors?**
- Orchestrator may ask before editing certain files; approve when reasonable
- Model files and secrets are denied — this is intentional

**Orchestrator won't delegate?**
- Ensure subagent names match exactly (ai-sentinel-graduation-judge, etc.)
- Check `permission.task` in orchestrator config allows delegation

---

**Last updated:** 2026-05-12 — AI-Sentinel multi-agent review system
