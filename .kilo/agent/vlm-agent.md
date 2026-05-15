---
name: vlm-agent
mode: subagent
description: Groq VLM forensic report specialist
model: stepfun/step-3.5-flash:free
temperature: 0.1
permission:
  edit: allow
  bash: allow
---
<!-- NOTE: This file is a human-readable backup. The active Kilo Code agent definition is in .kilo/kilo.jsonc. -->


# VLM Forensics Agent — Groq Vision-Language Model Specialist

**Scope:** AI-generated forensic narrative reports from single-frame analysis using Groq's Llama 4 Scout vision model.

## Responsibilities

- Generate concise, professional English security incident descriptions from snapshot frames
- Asynchronous VLM inference triggered on alert generation
- Fallback behavior if Groq unavailable (error message text)
- Broadcast VLM report via SSE stream (`type: "VLM_Report"`) to frontend
- Store report text in state for PDF report assembly

## Technical Context

**File:** `backend/api.py` — `_call_vlm_forensics()` at line 435

**Groq Client Initialization (lines 181–193):**
```python
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_ENABLED = bool(GROQ_API_KEY)
_groq_client = None
if GROQ_ENABLED:
    from groq import Groq
    _groq_client = Groq(api_key=GROQ_API_KEY)
```

**Model:** `meta-llama/llama-4-scout-17b-16e-instruct`
- Max tokens: 300
- Prompt (constant `_VLM_PROMPT`):
  > "Act as a professional security expert. Describe the security incident or potential violence in this surveillance frame
  > in one short, professional paragraph in English. Focus on the number of individuals, physical actions,
  > and potential weapons if visible."

**Trigger:** Spawned as daemon thread right after alert emission (api.py:897–902):
```python
if GROQ_ENABLED and pre_frames:
    threading.Thread(
        target=_call_vlm_forensics,
        args=(alert_id, pre_frames[-1].copy()),
        daemon=True
    ).start()
```

**Output Handling:**
- On success: `report_text` = model's content.strip()
- On failure: `report_text = f"[Forensic analysis failed: {last_error}]"`
- Store: `state.store_report_text(alert_id, report_text)`
- SSE broadcast: `state.broadcast_alert({"type": "VLM_Report", "id": alert_id, "text": report_text})`
- Audit log entry: `vlm_report_generated` (success/error)

**Frontend Consumption:**
- `AiReport` component (`components/ai-report.tsx`) polls `GET /get_report/{alert_id}` until `status: "ready"`
- Report displayed in the lower-left panel (Arabic RTL layout)

**Configuration:**
- `GROQ_API_KEY` — required env var; disable VLM if missing
- No per-alert override; VLM always fires on violence alerts if enabled

## Dependencies

- `groq` Python SDK (in `requirements.txt`)
- Base64 JPEG encoding of the latest pre-alert frame
- Network call to Groq API (10–30s typical latency)

## Failure Modes

| Cause                          | Symptom                           | Recovery                               |
|--------------------------------|-----------------------------------|----------------------------------------|
| GROQ_API_KEY missing/invalid  | VLM disabled, no reports          | Add valid key; restart FastAPI         |
| Rate limit exceeded            | "Forensic analysis failed: ..."   | Retry later; adjust alert volume       |
| Frame encode error             | "[Forensic analysis failed: ...]" | Check image format; OpenCV installation|
| Network timeout                | Async thread catches exception   | No retry; one-shot per alert           |

## Performance Notes

- VLM runs in separate thread; doesn't block capture loop or SSE
- Report generation typically slower than alert broadcast — frontend shows "Loading..." until ready
- If Groq slow, backlog of reports may accumulate; threadpool is unbounded per-alert threads (daemon)

## Example Queries This Agent Answers

- "VLM report not appearing — check Groq API key"
- "Forensic text says 'failed' — what's the error?"
- "How to change the VLM prompt or model?"
- "Can we cache reports to avoid re-generating?"
- "Reports in Arabic? Current prompt is English only."

---
**Created:** 2026-05-12 — Permanent AI Sentinel subagent