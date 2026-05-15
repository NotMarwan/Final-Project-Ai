# AI Sentinel — DeepSeek/OpenRouter Reporting System
**Date:** 2026-05-13
**Status:** Approved — ready for implementation

---

## Goal

Replace the Intelligence tab's passive Groq-SSE report display with an on-demand, structured incident report system powered by OpenRouter + DeepSeek. The official report engine becomes OpenRouter + DeepSeek. Existing Groq/VLM backend logic is preserved but no longer surfaces in the Intelligence tab UI.

---

## Scope

### In scope
- `backend/openrouter_reporting.py` — new `DeepSeekReportService` class
- 4 new FastAPI routes in `backend/api.py`
- `components/ai-report.tsx` — replace Groq/SSE UI with DeepSeek fetch/generate UI
- PDF backward-compatibility: inject DeepSeek summary section when available
- `backend/.env.example` — add OpenRouter env vars
- `backend/reports/` — JSON cache directory

### Out of scope
- Model weights, inference, training
- Telegram video delivery
- Live Monitor, Demo Clips
- Face Policy / Weapon UI
- Groq backend logic (kept as-is, untouched)
- Background tasks / SSE for report generation
- Git commit

---

## Architecture

```
Intelligence tab (browser)
  └─ AiReport component (components/ai-report.tsx)
       ├─ GET  /reports/deepseek/status       → key/model check on mount
       ├─ GET  /reports/deepseek/{alert_id}   → load cached report on alert select
       ├─ POST /reports/deepseek/{alert_id}   → generate / regenerate
       └─ POST /reports/deepseek/test         → smoke test (no alert needed)

FastAPI backend (backend/api.py)
  └─ DeepSeekReportService (backend/openrouter_reporting.py)
       ├─ Reads env (key never logged or returned)
       ├─ POST to https://openrouter.ai/api/v1/chat/completions (OpenAI-compatible)
       ├─ Parses strict JSON response
       └─ Reads/writes backend/reports/{alert_id}.json
```

---

## Environment Variables

All read via `python-dotenv` in `openrouter_reporting.py`. None returned to frontend.

| Variable | Default | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | *(required)* | Never logged, never sent to frontend |
| `OPENROUTER_MODEL` | `deepseek/deepseek-chat-v3.1` | Swappable: `deepseek/deepseek-r1`, `deepseek/deepseek-r1:free`, `deepseek/deepseek-chat-v3-0324` |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | |
| `OPENROUTER_TIMEOUT_SECONDS` | `45` | |
| `OPENROUTER_TEMPERATURE` | `0.2` | |

---

## `backend/openrouter_reporting.py`

### Class: `DeepSeekReportService`

```python
DeepSeekReportService()
  .is_configured() -> bool
  .status() -> dict          # safe: no key value
  .get_cached(alert_id) -> dict | None
  .generate(alert, force=False) -> dict
```

**`generate()` flow:**
1. If not `force`: check `backend/reports/{alert_id}.json` — return if present
2. Build prompt (system + user) from alert dict
3. POST to `{OPENROUTER_BASE_URL}/chat/completions` with timeout
4. Parse response content as JSON
5. On parse failure: wrap in `{ "executive_summary": <raw>, "raw": true }`
6. Write cache file: `{ alert_id, generated_at, model, report }`
7. Return cache envelope

**Cache file schema:**
```json
{
  "alert_id": "alert-123",
  "generated_at": "2026-05-13T12:00:00Z",
  "model": "deepseek/deepseek-chat-v3.1",
  "report": {
    "executive_summary": "...",
    "incident_type": "...",
    "severity_assessment": "...",
    "confidence_interpretation": "...",
    "timeline": ["..."],
    "camera_source": "...",
    "observed_evidence": "...",
    "risk_assessment": "...",
    "recommended_actions": ["..."],
    "demo_notes_for_graduation_committee": "...",
    "limitations": ["..."],
    "final_verdict": "..."
  }
}
```

**Test cache ID:** `test-demo-report` (stable; no real alert required)

---

## Prompt Design

**System message:**
> You are an AI Sentinel forensic incident report analyst. Generate a professional, concise surveillance incident report strictly from the provided alert metadata. Do not invent facts. If visual or video evidence is unavailable, state that explicitly. Output strict JSON only — no markdown, no code fences, no explanation text outside the JSON object.

**User message:** JSON object containing:
- `id`, `cameraId`, `timestamp`, `type`, `category`, `severity`, `confidence`
- `motionScore` (if present), `location`
- `evidenceClipAvailable: true/false`
- `thumbnailAvailable: true/false`
- `demoMode: true`
- `requestedFields: [list of 12 report fields]`

---

## API Endpoints

All under `/reports/deepseek/`. Auth: viewer-level (matching existing project pattern).

### `GET /reports/deepseek/status`
Returns (never returns key):
```json
{
  "enabled": true,
  "apiKeyPresent": true,
  "model": "deepseek/deepseek-chat-v3.1",
  "baseUrl": "https://openrouter.ai/api/v1",
  "cacheDirExists": true
}
```

### `POST /reports/deepseek/test`
- Uses hardcoded `DEMO_ALERT` payload (always works, no real alert needed)
- Optionally uses latest real alert if available (best-effort)
- Cache ID: `test-demo-report`
- Returns full cache envelope with report

### `POST /reports/deepseek/{alert_id}`
- Query param: `?force=true` to regenerate even if cached
- Requires alert to exist in `state`
- Returns full cache envelope

### `GET /reports/deepseek/{alert_id}`
- Returns cached envelope if present
- 404 `{ "detail": "Report not generated yet" }` if missing

---

## Frontend: `components/ai-report.tsx`

### Behaviour changes
| Before | After |
|---|---|
| Passive SSE listener for `VLM_Report` | No SSE listener (removed from this component) |
| Shows Groq-generated Arabic text | Shows DeepSeek JSON report in structured sections |
| "Groq LPU" badge | "DeepSeek via OpenRouter" badge |
| No generate button | "Generate DeepSeek Report" + "Regenerate" + "Copy Report" |

### State machine
```
idle              → alert selected → check_cache
check_cache       → cache hit      → ready
check_cache       → cache miss     → no_report
no_report         → user clicks Generate → loading
loading           → success        → ready
loading           → error          → error
ready             → user clicks Regenerate → loading
```

### Rendered report sections (from JSON fields)
1. Executive Summary
2. Incident Type + Severity Assessment
3. Confidence Interpretation
4. Timeline
5. Camera Source + Location
6. Observed Evidence
7. Risk Assessment
8. Recommended Actions
9. Limitations
10. Final Verdict
11. Demo Notes (collapsible or subtle)

### Error messages
- Missing key: "OpenRouter API key is missing. Add OPENROUTER_API_KEY to backend/.env and restart backend."
- Timeout: "Report generation timed out. Check backend logs."
- Generic: show error detail from API response

---

## PDF Backward-Compatibility

`/download_report/{alert_id}` is unchanged in signature and behavior.

In `api.py`, before calling `build_incident_pdf()`:
- Attempt `service.get_cached(alert_id)`
- If found: build `report_text` = concise string from `executive_summary` + `severity_assessment` + `recommended_actions` (joined) + `final_verdict`
- If not found: use existing `state.get_report_text(alert_id)` as before

No changes to `backend/reporting.py`.

---

## Safety Constraints

| Constraint | Status |
|---|---|
| No model weights touched | Guaranteed — no files in `backend/models/` or weight paths modified |
| No inference logic touched | `inference.py`, `live_alert_decision.py` untouched |
| No Groq backend logic removed | `_call_vlm_forensics` and Groq client in `api.py` untouched |
| No Telegram video delivery changed | `notifications.py` untouched |
| No Face Policy / Weapon UI restored | Not touched |
| API key backend-only | Key read only in `openrouter_reporting.py`, never sent to frontend |
| No commit | Validated only |

---

## Validation Checklist

1. `python -m py_compile backend/openrouter_reporting.py backend/api.py`
2. `npm run build` — zero TS errors
3. `GET /reports/deepseek/status` — `apiKeyPresent: false` (before key is added)
4. `POST /reports/deepseek/test` — graceful error when key missing
5. After user adds key to `.env` and restarts:
   - `GET /reports/deepseek/status` → `apiKeyPresent: true`
   - `POST /reports/deepseek/test` → structured JSON report returned
6. `GET /reports/deepseek/{existing_alert_id}` — 404 before generation
7. `POST /reports/deepseek/{existing_alert_id}` → full report
8. Frontend Intelligence tab: Generate button works, sections render, Copy works
9. `GET /download_report/{alert_id}` still returns PDF

---

## Files Changed

| File | Change |
|---|---|
| `backend/openrouter_reporting.py` | **New** — `DeepSeekReportService` |
| `backend/api.py` | Add 4 routes + import service + PDF injection |
| `backend/.env.example` | Add OpenRouter env vars |
| `components/ai-report.tsx` | Replace Groq/SSE UI with DeepSeek UI |
| `backend/reports/` | **New dir** — JSON report cache |
