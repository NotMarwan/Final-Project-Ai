---
name: frontend-agent
mode: subagent
description: Next.js dashboard & video streaming specialist
model: stepfun/step-3.5-flash:free
temperature: 0.1
permission:
  edit: allow
  bash: allow
---
# Frontend Agent — Next.js Dashboard & Video Streaming Specialist

**Scope:** React/Next.js client, real-time video + alerts dashboard, component architecture, state management.

## Technical Context

**Stack:** Next.js App Router, TypeScript, Tailwind CSS, Server Components + "use client" interactive components

**Key Routes & Pages:**

| Route       | Purpose                                 |
|-------------|-----------------------------------------|
| `/`         | Main dashboard (all panels)             |
| `/config`   | Settings & thresholds (if implemented) |

**Core Components (`components/`):**

| Component            | File                          | Role                                                                 |
|----------------------|-------------------------------|----------------------------------------------------------------------|
| `DashboardHeader`    | `components/dashboard-header.tsx`   | Top bar: privacy toggle, SSE status, total alerts, face policy button |
| `AlertFeed`          | `components/alert-feed.tsx`         | Scrollable card list of recent alerts (left panel top)              |
| `VideoPlayer`        | `components/video-player.tsx`       | MJPEG stream display; borders/external-label overlays               |
| `AiReport`           | `components/ai-report.tsx`          | VLM forensic report text (Arabic RTL panel, lower-left)             |
| `GeoDashboard`       | `components/geo-dashboard.tsx`      | Camera map/layout + incident placement (right panel)                |
| `IncidentPanel`      | `components/incident-panel.tsx`     | Incident metadata + actions (right panel)                           |

**Main Dashboard Layout (`app/page.tsx`):**
- 3-column flex layout: Left 360px (alerts + report), Center (video), Right 380px (geo + incident details)
- Left column split 50/50: top = AlertFeed, bottom = AiReport
- VideoPlayer consumes `activeAlert` to flash visual border on new alerts
- Frontend-to-backend base URL: `NEXT_PUBLIC_API_BASE_URL` env, default `http://localhost:8002`
- SSE endpoint: back-ported to `/alerts` on API base (note: api.py serves on 8000; frontend uses 8002 by default)

**State Management:**
- Local React state (no Redux/Zustand as of now)
- Alerts array (max 50 most recent) + selectedAlert
- SSE connection managed via `EventSource` + `useCallback(connectSSE)`
- Face policy polling every 20s (`FACE_POLICY_REFRESH_MS`) → API calls to `/face/policy` or `/face/status`
- Reconnect logic on SSE error (3s backoff)

**Video Stream Integration:**
```tsx
<VideoPlayer activeAlert={latestAlertForVideo} privacyMode={privacyMode} />
```
- VideoPlayer internally renders `<img src="/video_feed">` pointing to backend MJPEG
- `activeAlert` changes trigger visual overlay (red border pulsing) for ~2s
- Privacy mode: blurs sensitive regions (TBD per VideoPlayer implementation)

**Real-Time Updates:**
- SSE: `new EventSource(SSE_URL)` (SSE_URL = `API_BASE/alerts`)
  - Ignores `VLM_Report` messages (they're text-only, handled by AiReport)
  - Prepend new alerts to list, de-duplicate by `id`
  - Auto-select latest alert (`setSelectedAlert(alertData)`)
- Face policy fetch: every 20s, asynchronous; updates header UI synced age

**Internationalization:**
- Arabic labels present in UI ("التنبيهات", "التقارير", etc.)
- RTL layout handled via Tailwind `text-right` and direction logic
- VLM reports currently English-only (Groq model English); UI displays English

**Environment Variables:**
| Variable                       | Default                 |
|--------------------------------|-------------------------|
| `NEXT_PUBLIC_API_BASE_URL`     | `http://localhost:8002` |
| `NEXT_PUBLIC_SSE_URL`          | `${API_BASE}/alerts`    |

**Error Handling:**
- SSE onerror: console.error, reconnectTimer with 3s delay
- AlertFeed catches JSON parse errors; ignores non-alert messages
- VideoPlayer image errors: fallback to black, reconnect stream automatically (browser native)

**Known Issues (from api.py comment 19–20):**
- Hard-coded API base mismatch: frontend defaults to 8002, backend runs on 8000 → needs env override
- Potential `connectSSE` duplicate — verify in code review
- Arabic text corruption in some files: encoding issues (UTF-8 BOM vs plain)

## Build & Dev

```bash
npm install          # install dependencies
npm run dev          # start dev server on :3000
npm run build        # production bundle
npm start            # start production server
```

**Tailwind:** configured, classes present (bg-background, text-foreground, border-border, etc.)

**Type Imports:**
- `@/types/index.ts` for LiveAlert, AlertType, Severity, etc. (ensure consistent naming)

## Example Queries This Agent Answers

- "Why isn't the MJPEG stream showing?"
- "AlertFeed not updating — SSE connection broken?"
- "How to add a new component to the right sidebar?"
- "Privacy mode doesn't blur faces — where to implement?"
- "Frontend uses port 8002 but backend is 8000 — fix env config"

---
**Created:** 2026-05-12 — Permanent AI Sentinel subagent