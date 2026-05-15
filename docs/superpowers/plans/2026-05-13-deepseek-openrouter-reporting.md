# DeepSeek/OpenRouter Reporting System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a DeepSeek/OpenRouter on-demand incident report system to AI Sentinel, replacing the Intelligence tab's passive Groq UI with structured JSON reports generated via OpenRouter.

**Architecture:** `DeepSeekReportService` in `backend/openrouter_reporting.py` handles all OpenRouter API calls and JSON file caching. Four new FastAPI routes in `backend/api.py` expose the service. `components/ai-report.tsx` is rewritten to fetch/generate reports via REST instead of listening to Groq SSE.

**Tech Stack:** Python `urllib` (stdlib, no new deps), FastAPI, Next.js/React, TypeScript

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/openrouter_reporting.py` | **Create** | `DeepSeekReportService` — env config, OpenRouter call, JSON cache |
| `backend/api.py` | **Modify** | Import service; 4 new routes; PDF DeepSeek injection in `download_report` |
| `components/ai-report.tsx` | **Modify** | Replace Groq/SSE UI with DeepSeek fetch/generate UI |
| `backend/.env.example` | **Modify** | Add OpenRouter env vars |

---

## Task 1: Create `backend/openrouter_reporting.py`

**Files:**
- Create: `backend/openrouter_reporting.py`

- [ ] **Step 1: Create the file with full implementation**

Write `backend/openrouter_reporting.py` with this exact content:

```python
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=True)

_DEMO_ALERT: dict[str, Any] = {
    "id": "test-demo-report",
    "cameraId": "CAM-01",
    "timestamp": "00:00:00 UTC",
    "type": "Intrusion",
    "category": "intrusion",
    "severity": "high",
    "confidence": 88.5,
    "motionScore": 0.72,
    "location": "Main Entrance",
    "evidenceClipAvailable": False,
    "thumbnailAvailable": False,
    "demoMode": True,
}

_REPORT_FIELDS = [
    "executive_summary",
    "incident_type",
    "severity_assessment",
    "confidence_interpretation",
    "timeline",
    "camera_source",
    "observed_evidence",
    "risk_assessment",
    "recommended_actions",
    "demo_notes_for_graduation_committee",
    "limitations",
    "final_verdict",
]

_SYSTEM_PROMPT = (
    "You are an AI Sentinel forensic incident report analyst. "
    "Generate a professional, concise surveillance incident report strictly from "
    "the provided alert metadata. Do not invent facts. If visual or video evidence "
    "is unavailable, state that explicitly. "
    "Output strict JSON only — no markdown, no code fences, no explanation text "
    "outside the JSON object."
)


class DeepSeekReportService:
    def __init__(self, cache_dir: Path | str | None = None) -> None:
        self._api_key: str = os.getenv("OPENROUTER_API_KEY", "")
        self._model: str = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3.1")
        self._base_url: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        self._timeout: float = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "45"))
        self._temperature: float = float(os.getenv("OPENROUTER_TEMPERATURE", "0.2"))

        if cache_dir is None:
            cache_dir = Path(__file__).resolve().parent / "reports"
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def status(self) -> dict:
        return {
            "enabled": self.is_configured(),
            "apiKeyPresent": self.is_configured(),
            "model": self._model,
            "baseUrl": self._base_url,
            "cacheDirExists": self._cache_dir.exists(),
        }

    def get_cached(self, alert_id: str) -> dict | None:
        path = self._cache_dir / f"{alert_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def generate(self, alert: dict, force: bool = False) -> dict:
        """Generate (or return cached) DeepSeek report for the given alert dict.

        Raises ValueError if API key is missing.
        Raises RuntimeError on HTTP/parse failure.
        Raises TimeoutError on timeout.
        """
        alert_id = str(alert.get("id", "unknown"))

        if not force:
            cached = self.get_cached(alert_id)
            if cached is not None:
                return cached

        if not self.is_configured():
            raise ValueError(
                "OPENROUTER_API_KEY is not set. "
                "Add it to backend/.env and restart the backend."
            )

        report_obj = self._call_openrouter(alert)
        envelope: dict = {
            "alert_id": alert_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": self._model,
            "report": report_obj,
        }

        path = self._cache_dir / f"{alert_id}.json"
        path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
        return envelope

    def demo_alert(self) -> dict:
        """Return the hardcoded demo alert used by the test endpoint."""
        return dict(_DEMO_ALERT)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_openrouter(self, alert: dict) -> dict:
        user_payload: dict = {
            k: alert.get(k)
            for k in (
                "id", "cameraId", "timestamp", "type", "category",
                "severity", "confidence", "motionScore", "location",
                "evidenceClipAvailable", "thumbnailAvailable", "demoMode",
            )
        }
        user_payload["requestedFields"] = _REPORT_FIELDS

        body = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                "temperature": self._temperature,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ai-sentinel.demo",
                "X-Title": "AI Sentinel",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter HTTP {exc.code}: {error_body[:400]}") from exc
        except TimeoutError as exc:
            raise TimeoutError("OpenRouter request timed out after "
                               f"{int(self._timeout)}s.") from exc

        try:
            data = json.loads(raw)
            content: str = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Unexpected OpenRouter response format: {raw[:300]}"
            ) from exc

        # Strip optional markdown code fences DeepSeek sometimes adds
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"executive_summary": content, "raw": True}
```

- [ ] **Step 2: Verify syntax**

```bash
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -m py_compile openrouter_reporting.py
echo Exit code: $?
```

Expected: no output, exit code 0.

---

## Task 2: Add 4 FastAPI routes to `backend/api.py`

**Files:**
- Modify: `backend/api.py` (near line 1737, before `download_report`)

- [ ] **Step 1: Add import of DeepSeekReportService near top of api.py**

Find this block near the top of `api.py` (around line 40–66 in the `_get_imports` / `try/except` pattern). The file uses `load_dotenv(override=True)` at line 99. Add the import and singleton instantiation right **after** the `REPORTS_DIR.mkdir` line (around line 274).

Find this exact line in `api.py`:
```python
REPORTS_DIR.mkdir(exist_ok=True)
```

Add immediately after it:

```python

try:
    from .openrouter_reporting import DeepSeekReportService
except ImportError:
    from openrouter_reporting import DeepSeekReportService

deepseek_service = DeepSeekReportService(cache_dir=REPORTS_DIR)
```

- [ ] **Step 2: Add the 4 route handlers**

Find this exact line in `api.py`:
```python
@app.get("/download_report/{alert_id}", summary="Fetch forensic PDF report")
```

Insert the following block **immediately before** that line (leave a blank line before and after):

```python
# ─────────────────────────────────────────────────────────────────────────────
# DeepSeek / OpenRouter Reporting
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/reports/deepseek/status", summary="DeepSeek report service status")
async def deepseek_status():
    return deepseek_service.status()


@app.post("/reports/deepseek/test", summary="Generate test DeepSeek report (no alert required)")
async def deepseek_test(request: Request):
    security_controller.authorize(request, required_role="viewer")
    demo = deepseek_service.demo_alert()
    # Best-effort: use the latest real alert if any exist
    all_alerts = state.get_all_alerts()
    if all_alerts:
        latest = sorted(all_alerts, key=lambda a: a.get("isoTime", ""), reverse=True)[0]
        demo = {**latest, "id": "test-demo-report", "demoMode": True}

    try:
        result = deepseek_service.generate(demo, force=True)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/reports/deepseek/{alert_id}", summary="Generate DeepSeek report for an alert")
async def deepseek_generate(alert_id: str, request: Request, force: bool = False):
    _validate_alert_id(alert_id)
    security_controller.authorize(request, required_role="viewer")
    alert = state.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Incident not found")
    alert_payload = {**alert, "demoMode": False}
    try:
        result = deepseek_service.generate(alert_payload, force=force)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/reports/deepseek/{alert_id}", summary="Fetch cached DeepSeek report")
async def deepseek_get(alert_id: str, request: Request):
    _validate_alert_id(alert_id)
    security_controller.authorize(request, required_role="viewer")
    cached = deepseek_service.get_cached(alert_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="Report not generated yet")
    return cached


```

- [ ] **Step 3: Check `state.get_all_alerts()` exists**

Run:
```bash
grep -n "def get_all_alerts" backend/api.py
```

If it exists, proceed. If not, find the method that returns all alerts (likely `get_alerts` or similar):
```bash
grep -n "def get_alert" backend/api.py
```

If the method is named differently (e.g. `get_alerts()`), update the test route accordingly:
- `state.get_all_alerts()` → whatever the correct method is

The method should return a list of alert dicts.

- [ ] **Step 4: Verify syntax**

```bash
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -m py_compile api.py
echo Exit code: $?
```

Expected: no output, exit code 0. If there are errors, fix and re-run.

---

## Task 3: PDF backward-compat — inject DeepSeek section into `download_report`

**Files:**
- Modify: `backend/api.py` around line 1746 (the `download_report` function)

- [ ] **Step 1: Update `report_text` derivation in `download_report`**

Find this exact block inside `async def download_report`:
```python
    report_text = state.get_report_text(alert_id) or "Visual analysis is still pending."
```

Replace it with:

```python
    # Prefer DeepSeek report if available; fall back to Groq text
    _deepseek_cache = deepseek_service.get_cached(alert_id)
    if _deepseek_cache and isinstance(_deepseek_cache.get("report"), dict):
        _r = _deepseek_cache["report"]
        _sections = []
        if _r.get("executive_summary"):
            _sections.append(f"Summary: {_r['executive_summary']}")
        if _r.get("severity_assessment"):
            _sections.append(f"Severity: {_r['severity_assessment']}")
        if _r.get("recommended_actions"):
            _actions = _r["recommended_actions"]
            if isinstance(_actions, list):
                _sections.append("Actions: " + "; ".join(str(a) for a in _actions[:3]))
            else:
                _sections.append(f"Actions: {_actions}")
        if _r.get("final_verdict"):
            _sections.append(f"Verdict: {_r['final_verdict']}")
        report_text = "\n".join(_sections) if _sections else "DeepSeek report available (no text fields)."
    else:
        report_text = state.get_report_text(alert_id) or "Visual analysis is still pending."
```

- [ ] **Step 2: Verify syntax**

```bash
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -m py_compile api.py
echo Exit code: $?
```

Expected: exit code 0.

---

## Task 4: Rewrite `components/ai-report.tsx`

**Files:**
- Modify: `components/ai-report.tsx`

- [ ] **Step 1: Replace the entire file content**

Write `components/ai-report.tsx` with this exact content:

```tsx
"use client"

import { useState, useEffect, useCallback } from "react"
import {
  FileSearch,
  Sparkles,
  Loader2,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Copy,
  ClipboardCheck,
} from "lucide-react"
import { cn } from "@/lib/utils"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

interface ReportData {
  executive_summary?: string
  incident_type?: string
  severity_assessment?: string
  confidence_interpretation?: string
  timeline?: string | string[]
  camera_source?: string
  observed_evidence?: string
  risk_assessment?: string
  recommended_actions?: string | string[]
  demo_notes_for_graduation_committee?: string
  limitations?: string | string[]
  final_verdict?: string
  raw?: boolean
}

interface ReportEnvelope {
  alert_id: string
  generated_at: string
  model: string
  report: ReportData
}

type State =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "no_report" }
  | { status: "generating" }
  | { status: "ready"; data: ReportEnvelope }
  | { status: "error"; message: string }

interface AiReportProps {
  alertId: string | undefined
}

function toLines(value: string | string[] | undefined): string[] {
  if (!value) return []
  if (Array.isArray(value)) return value.map(String).filter(Boolean)
  return [String(value)]
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-[10px] font-bold uppercase tracking-widest text-primary/70">{label}</p>
      <div className="text-[12px] leading-relaxed text-foreground">{children}</div>
    </div>
  )
}

export function AiReport({ alertId }: AiReportProps) {
  const [state, setState] = useState<State>({ status: "idle" })
  const [copied, setCopied] = useState(false)
  const [missingKey, setMissingKey] = useState(false)

  // Check if API key is configured on mount
  useEffect(() => {
    fetch(`${API_BASE}/reports/deepseek/status`)
      .then((r) => r.json())
      .then((d) => setMissingKey(!d.apiKeyPresent))
      .catch(() => {})
  }, [])

  // Load cached report when alert changes
  useEffect(() => {
    if (!alertId) {
      setState({ status: "idle" })
      return
    }

    setState({ status: "checking" })

    fetch(`${API_BASE}/reports/deepseek/${encodeURIComponent(alertId)}`)
      .then(async (r) => {
        if (r.status === 404) {
          setState({ status: "no_report" })
          return
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data: ReportEnvelope = await r.json()
        setState({ status: "ready", data })
      })
      .catch(() => setState({ status: "no_report" }))
  }, [alertId])

  const generate = useCallback(
    async (force = false) => {
      if (!alertId) return
      setState({ status: "generating" })
      try {
        const r = await fetch(
          `${API_BASE}/reports/deepseek/${encodeURIComponent(alertId)}?force=${force}`,
          { method: "POST" }
        )
        const body = await r.json()
        if (!r.ok) {
          const msg: string = body?.detail ?? `HTTP ${r.status}`
          setState({
            status: "error",
            message: msg.includes("OPENROUTER_API_KEY")
              ? "OpenRouter API key is missing. Add OPENROUTER_API_KEY to backend/.env and restart backend."
              : msg,
          })
          return
        }
        setState({ status: "ready", data: body as ReportEnvelope })
      } catch {
        setState({ status: "error", message: "Network error — is the backend running?" })
      }
    },
    [alertId]
  )

  const copyReport = useCallback(async () => {
    if (state.status !== "ready") return
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(state.data.report, null, 2)
      )
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }, [state])

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden flex flex-col h-full shadow-inner">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center gap-2 border-b border-border px-4 py-2.5 bg-muted/20">
        <FileSearch className="h-3.5 w-3.5 text-primary" />
        <span className="text-xs font-semibold text-foreground">DeepSeek Incident Report</span>
        <div className="ml-auto flex items-center gap-1.5 border border-primary/20 bg-primary/5 px-2 py-0.5 rounded-md">
          <Sparkles className="h-3 w-3 text-primary" />
          <span className="font-mono text-[9px] text-primary uppercase tracking-wider font-bold">
            DeepSeek via OpenRouter
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-4">

        {/* Missing key banner */}
        {missingKey && (
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-400" />
            <p className="text-[11px] leading-relaxed text-amber-300 font-medium">
              OpenRouter API key is missing. Add <code className="font-mono">OPENROUTER_API_KEY</code> to{" "}
              <code className="font-mono">backend/.env</code> and restart backend.
            </p>
          </div>
        )}

        {state.status === "idle" && (
          <div className="flex h-full flex-col items-center justify-center gap-2 py-6 text-center text-muted-foreground/50 border border-dashed border-border/70 rounded-lg">
            <FileSearch className="h-8 w-8 opacity-40" />
            <p className="text-xs font-medium">Select an incident to generate a report.</p>
          </div>
        )}

        {state.status === "checking" && (
          <div className="flex h-full items-center justify-center gap-2 text-muted-foreground/60">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-xs">Loading…</span>
          </div>
        )}

        {state.status === "no_report" && (
          <div className="flex h-full flex-col items-center justify-center gap-4 py-8 text-center border border-dashed border-border/70 rounded-lg">
            <FileSearch className="h-8 w-8 text-muted-foreground/40" />
            <div>
              <p className="text-xs font-medium text-foreground">No report for this incident yet.</p>
              <p className="mt-1 text-[10px] text-muted-foreground">
                DeepSeek will analyse the alert metadata and generate a structured forensic report.
              </p>
            </div>
            <button
              onClick={() => generate(false)}
              disabled={missingKey}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                missingKey
                  ? "bg-muted text-muted-foreground cursor-not-allowed"
                  : "bg-primary text-primary-foreground hover:bg-primary/90"
              )}
            >
              <Sparkles className="h-3.5 w-3.5" />
              Generate DeepSeek Report
            </button>
          </div>
        )}

        {state.status === "generating" && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center py-4">
            <div className="relative flex h-10 w-10 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/20" />
              <Loader2 className="relative h-5 w-5 text-primary animate-spin" />
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">Contacting DeepSeek via OpenRouter…</p>
              <p className="mt-1 text-[10px] text-muted-foreground leading-relaxed">
                Generating structured incident report. This may take up to 45 seconds.
              </p>
            </div>
          </div>
        )}

        {state.status === "error" && (
          <div className="space-y-3">
            <div className="flex items-start gap-2.5 rounded-lg border border-destructive/20 bg-destructive/5 p-3.5">
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-destructive" />
              <p className="text-[11px] leading-relaxed text-destructive/90 font-medium">
                {state.message}
              </p>
            </div>
            {alertId && (
              <button
                onClick={() => generate(false)}
                className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted/50 transition-colors"
              >
                <RefreshCw className="h-3 w-3" />
                Try again
              </button>
            )}
          </div>
        )}

        {state.status === "ready" && (
          <div className="space-y-4">
            {/* Action buttons */}
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={() => generate(true)}
                className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[11px] font-medium hover:bg-muted/50 transition-colors"
              >
                <RefreshCw className="h-3 w-3" />
                Regenerate
              </button>
              <button
                onClick={copyReport}
                className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[11px] font-medium hover:bg-muted/50 transition-colors"
              >
                {copied ? (
                  <>
                    <ClipboardCheck className="h-3 w-3 text-green-500" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    Copy Report
                  </>
                )}
              </button>
              <span className="ml-auto text-[9px] text-muted-foreground font-mono">
                {state.data.model} · {new Date(state.data.generated_at).toLocaleTimeString()}
              </span>
            </div>

            {/* Report sections */}
            <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/5 p-3.5">
              {state.data.report.raw && (
                <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-[10px] text-amber-300">
                  Note: Model returned unstructured text — displaying as-is.
                </div>
              )}

              {state.data.report.executive_summary && (
                <Section label="Executive Summary">
                  {state.data.report.executive_summary}
                </Section>
              )}

              {(state.data.report.incident_type || state.data.report.severity_assessment) && (
                <div className="grid grid-cols-2 gap-3">
                  {state.data.report.incident_type && (
                    <Section label="Incident Type">{state.data.report.incident_type}</Section>
                  )}
                  {state.data.report.severity_assessment && (
                    <Section label="Severity">{state.data.report.severity_assessment}</Section>
                  )}
                </div>
              )}

              {state.data.report.confidence_interpretation && (
                <Section label="Confidence Interpretation">
                  {state.data.report.confidence_interpretation}
                </Section>
              )}

              {state.data.report.timeline && toLines(state.data.report.timeline).length > 0 && (
                <Section label="Timeline">
                  <ul className="list-disc list-inside space-y-0.5">
                    {toLines(state.data.report.timeline).map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {state.data.report.camera_source && (
                <Section label="Camera / Location">{state.data.report.camera_source}</Section>
              )}

              {state.data.report.observed_evidence && (
                <Section label="Observed Evidence">{state.data.report.observed_evidence}</Section>
              )}

              {state.data.report.risk_assessment && (
                <Section label="Risk Assessment">{state.data.report.risk_assessment}</Section>
              )}

              {state.data.report.recommended_actions &&
                toLines(state.data.report.recommended_actions).length > 0 && (
                  <Section label="Recommended Actions">
                    <ul className="list-disc list-inside space-y-0.5">
                      {toLines(state.data.report.recommended_actions).map((a, i) => (
                        <li key={i}>{a}</li>
                      ))}
                    </ul>
                  </Section>
                )}

              {state.data.report.limitations &&
                toLines(state.data.report.limitations).length > 0 && (
                  <Section label="Limitations">
                    <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                      {toLines(state.data.report.limitations).map((l, i) => (
                        <li key={i}>{l}</li>
                      ))}
                    </ul>
                  </Section>
                )}

              {state.data.report.final_verdict && (
                <Section label="Final Verdict">
                  <span className="font-semibold">{state.data.report.final_verdict}</span>
                </Section>
              )}

              {state.data.report.demo_notes_for_graduation_committee && (
                <details className="group">
                  <summary className="cursor-pointer text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60 hover:text-muted-foreground transition-colors">
                    Demo Notes ▸
                  </summary>
                  <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                    {state.data.report.demo_notes_for_graduation_committee}
                  </p>
                </details>
              )}
            </div>

            <p className="flex items-center gap-1.5 text-[9px] text-muted-foreground font-medium pt-1 border-t border-border/50">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              Generated by DeepSeek via OpenRouter from alert metadata only. Evidence based on system records.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
```

---

## Task 5: Update `backend/.env.example`

**Files:**
- Modify: `backend/.env.example`

- [ ] **Step 1: Append OpenRouter vars to .env.example**

Find the last line of `backend/.env.example` (currently ends with `CAM3_SOURCE=cam3.mp4`).

Add after it:

```
# OpenRouter / DeepSeek Reporting
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=deepseek/deepseek-chat-v3.1
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_TIMEOUT_SECONDS=45
OPENROUTER_TEMPERATURE=0.2
```

---

## Task 6: Fix `state.get_all_alerts()` if missing

**Files:**
- Modify: `backend/api.py` (AppState class, around line 369)

This step is conditional. Only perform it if Step 3 of Task 2 revealed `get_all_alerts` does not exist.

- [ ] **Step 1: Check if get_all_alerts exists**

```bash
grep -n "def get_all_alerts\|def get_alerts\|_alerts" backend/api.py | head -20
```

- [ ] **Step 2: If missing, add method to AppState**

Find the `get_alert` method in the `AppState` class:
```python
    def get_alert(self, alert_id: str) -> Optional[dict]:
```

Add this method immediately after it:
```python
    def get_all_alerts(self) -> list:
        with self._alert_lock:
            return list(self._alerts.values())
```

(The exact lock name may differ — use whichever lock guards `self._alerts` in the existing code.)

- [ ] **Step 3: Verify syntax**

```bash
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -m py_compile api.py
```

---

## Task 7: Full validation

- [ ] **Step 1: Compile both backend files**

```bash
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -m py_compile openrouter_reporting.py api.py
echo "Compile result: $?"
```

Expected: no output, exit 0.

- [ ] **Step 2: Build frontend**

```bash
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel"
npm run build
```

Expected: build completes with 0 TypeScript errors. Note any warnings.

- [ ] **Step 3: Start backend (without OpenRouter key)**

```bash
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel\backend"
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

In a second terminal:

```bash
curl http://localhost:8000/reports/deepseek/status
```

Expected response:
```json
{"enabled":false,"apiKeyPresent":false,"model":"deepseek/deepseek-chat-v3.1","baseUrl":"https://openrouter.ai/api/v1","cacheDirExists":true}
```

- [ ] **Step 4: Test graceful missing-key error**

```bash
curl -X POST http://localhost:8000/reports/deepseek/test
```

Expected response (503):
```json
{"detail":"OPENROUTER_API_KEY is not set. Add it to backend/.env and restart the backend."}
```

- [ ] **Step 5: Add key and restart**

Add to `backend/.env`:
```
OPENROUTER_API_KEY=<your_key>
```

Restart backend. Then:

```bash
curl http://localhost:8000/reports/deepseek/status
```

Expected: `"apiKeyPresent":true`

- [ ] **Step 6: Test report generation**

```bash
curl -X POST http://localhost:8000/reports/deepseek/test
```

Expected: JSON envelope with `alert_id`, `model`, `generated_at`, and `report` object containing all 12 fields.

- [ ] **Step 7: Start frontend and verify Intelligence tab**

```bash
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel"
npm start
```

Open browser → Intelligence tab:
- Header shows "DeepSeek Incident Report" + "DeepSeek via OpenRouter" badge
- Selecting an alert with no cached report shows "Generate DeepSeek Report" button
- Clicking Generate shows spinner, then structured sections
- Regenerate overwrites cache
- Copy copies JSON to clipboard

- [ ] **Step 8: Verify nothing broken**

- `GET /download_report/{alert_id}` still returns PDF
- Demo Clips tab still works
- Live Monitor still works
- Telegram status endpoint still works
- No port 8002 errors (frontend should be on 3000, backend on 8000)
- No Face Policy / Weapon UI visible

---

## Final Report Template

After all tasks complete, provide this summary:

```
FILES CHANGED:
  backend/openrouter_reporting.py    [CREATED]
  backend/api.py                     [MODIFIED — 4 routes + PDF injection]
  components/ai-report.tsx           [MODIFIED — DeepSeek UI]
  backend/.env.example               [MODIFIED — OpenRouter vars]
  backend/reports/                   [CREATED DIR]

ENDPOINTS ADDED:
  GET  /reports/deepseek/status
  POST /reports/deepseek/test
  POST /reports/deepseek/{alert_id}
  GET  /reports/deepseek/{alert_id}

ENV VARS REQUIRED:
  OPENROUTER_API_KEY        (required)
  OPENROUTER_MODEL          (default: deepseek/deepseek-chat-v3.1)
  OPENROUTER_BASE_URL       (default: https://openrouter.ai/api/v1)
  OPENROUTER_TIMEOUT_SECONDS (default: 45)
  OPENROUTER_TEMPERATURE    (default: 0.2)

MODEL USED:       deepseek/deepseek-chat-v3.1 (from env)
KEY DETECTED:     [yes/no — do not print value]

BACKEND COMPILE:  [PASS/FAIL]
FRONTEND BUILD:   [PASS/FAIL — note any warnings]

/reports/deepseek/status:  [response]
/reports/deepseek/test:    [PASS with structured JSON / FAIL with error]

GROQ/VLM INTACT:      yes — backend untouched
TELEGRAM INTACT:      yes — untouched
DEMO CLIPS INTACT:    yes — untouched
FACE/WEAPON UI:       not present — confirmed

FINAL: GO / NO-GO
```
