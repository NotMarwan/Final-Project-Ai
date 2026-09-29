---
authority: scoped
non_authoritative: true
---

# WT-26 blueprint delta + ui-contract delta (slice S-13, statistics & dashboard correctness)

Worktree `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-26`, branch `codex/sentinel-26-stats`, baseline
`e86d34b5d16abcc133ad3470c8d135d00b2423d4`. Registry consulted: `wt-03/docs/blueprint/INDEX.md` + `index.json`
(seed commit `27c18d2`). IDs used exactly as registered; one new ID allocated below (pending registry confirmation).

## 1. ID deltas

| ID | Was | Now | Evidence |
|---|---|---|---|
| S-13 (slice, stats/overview analytics) | `unverified` | **`implemented-active`** | this worktree's commits; limitation "client-side-only aggregation; no server stats endpoint exists" is now **resolved in part** — `GET /stats/overview` exists (new feature ID to be assigned by the integrator from F-58+) but aggregates the **evidence ledger** (evidence-record scope), not a complete alert store; session buffer remains the only complete alert source |
| U-01 (Overview) | `partial` | **`partial` (unchanged status, updated limitations)** | limitation "client-side-only aggregation" updated as above; "Active-cameras stat hardcoded honest unavailable (G-3)" **remains by design** (no camera-presence endpoint consumed; kept honest) |
| design-map G-5 (contrast/a11y) | open | **stale/medium bullet RESOLVED; others remain** | `--state-stale` no longer equals `--threat-medium` in either theme (dark `#9db4d6`, 8.76:1 on `--surface-1`; light `#4a6284`, 6.23:1 on `#ffffff`; both measured, WCAG 1.4.3 AA). Remaining G-5 bullets (10px tertiary text, light-theme sweep, toast stacking, hover cross-highlight) — hover cross-highlight now has keyboard equivalents (legend focus, camera-row focus, Shift+Arrow brush); the rest stay open |
| design-map G-6 (chart/stats surface) | open | **documented + tested** | filter-logic exact semantics now live in `lib/sentinel-selectors.ts#chartDimensionSets` + tests (`lib/__tests__/sentinel-selectors-stats.test.mjs`) and `docs/campaign/engineering/26-stats-semantics.md` §3 |
| design-map G-8 (manifest drift) | open | **RESOLVED** | `app/manifest.ts:11-12` `theme_color`/`background_color` = `#090c0e` = `--surface-0` |
| design-map G-10 (session-scoped data) | open | **partially addressed** | 50-alert cap now surfaced in UI ("الجلسة (حد أقصى 50)"), session-start stamp + cap warning shown, previous-window deltas suppressed when unobserved; historical restore still absent (needs history API — outside S-13) |
| **F-## (NEW — integrator assigns from F-58 upward per orchestrator ID ruling)** | — | **`implemented-active`** | Additive `GET /stats/overview` route aggregating `evidence_ledger.jsonl` with explicit window + camera scope. WT-26 proposes NO number (F-50 is taken by WT-22; allocation is integrator-side from F-58). No code references any ID — registry-only label. |

## 2. api.py hunks for the integrator (SC-1, flagged)

Single contiguous region, `backend/api.py:1484-1493`:
1. `1484-1490` — comment block + `try: from .stats_service import build_stats_router except ImportError: from stats_service import build_stats_router`
2. `1492-1493` — `app = FastAPI(...)` (unchanged line) + `app.include_router(build_stats_router(lambda: evidence_ledger, lambda: security_controller))`

New files owned by WT-26: `backend/stats_service.py`, `backend/tests/test_stats_service.py`.
No other backend files touched. No cherry-picks performed (module-level + TestClient verification used instead).

## 3. ui-contract delta — `GET /stats/overview` payload (SC-4-adjacent, additive)

Request: `GET /stats/overview?from=<ISO-8601 with tz>&to=<ISO-8601 with tz>[&cameraId=<exact>]`
Auth: `security_controller.authorize(request, required_role="viewer")` (same as `/evidence_chain/{alert_id}`).
Validation: missing/naive/invalid timestamps → 400; `to <= from` → 400; span > 366 days → 400.

Response 200 (see `backend/stats_service.py#build_overview_stats`):

```jsonc
{
  "scope": "evidence-ledger",          // FIXED: counts are EVIDENCE RECORDS, not alerts
  "timeField": "evidenceWriteTimeUtc",  // window applies to evidence-write time, not alert time
  "window": { "from": "<iso>", "to": "<iso>" },   // closed [from, to]
  "cameraId": null,                     // null = all cameras; else exact match
  "recordCount": 0,
  "bySeverity": { "critical": 0, "high": 0, "medium": 0, "other": 0 },
  "byCamera": { "CAM-01": 0 },
  "assets": { "withClip": 0, "withSnapshot": 0, "withReport": 0 },
  "firstRecordAt": null, "lastRecordAt": null,
  "skippedRecords": 0,                  // records with unusable timestamps, counted not hidden
  "typeBreakdown": null,                // NOT SUPPLIED by the ledger — explicit unavailable
  "latency": null,                      // NOT SUPPLIED by the ledger — explicit unavailable
  "previousWindow": { "from": "<iso>", "to": "<iso>", "recordCount": 0 },
  "ledger": { "path": "...", "exists": true, "totalRecords": 0 },
  "generatedAt": "<iso>"
}
```

Failure states: 503 `evidence ledger is not initialized` | 503 `evidence ledger integrity check failed`
(hash-chain validation failure or unreadable ledger). The frontend falls back to session-scope numbers and
labels the fallback reason (`components/overview/use-overview-stats.ts`).

Frontend consumption: `useOverviewStats` (fetch window quantised to the minute; cameraId from CrossFilters).
Charts intentionally remain session-scoped (the ledger carries no per-alert series) and say so in the UI.

## 4. CrossFilters handoff contract (coordination with WT-25)

`CrossFilters` shape **unchanged** (`{ cameraId?, type?, severity?, confidenceBand?, range }`). Stat-card
drill-through applies the same shared filters via `setFilters` and opens the first matching alert through
`onSelectIncident` (page.tsx navigates to the incidents section). The overview-local brush window is NOT part
of CrossFilters; brushed views label the limitation in-page ("الفترة المحددة بالسحب تُطبَّق هنا فقط"). If WT-25
extends CrossFilters with a time-window field, WT-26 will adopt it instead of the label workaround.

## 5. Counting semantics delivered (exact definitions, also rendered in the UI legend)

D1 تنبيه (alert) = one confirmed decision-contract decision on SSE `/alerts` — the unit of every overview number.
D2 كشف (detection) = per-frame model read — never counted in the overview.
D3 أشخاص ظاهرون = persons in the latest processed frame (instantaneous; monitor screen).
D4 أشخاص متبَّعون فريدون خلال الفترة = distinct track ids in a window — **not supplied by any registered source; UI says so**.
D5 زمن احتساب القرار = server payload-build latency (perf_counter at `api.py:964`) — never "glass-to-alert"; stream snapshots carry `None` (`pipeline_render.py:228`) and are excluded from percentiles (sample count `n` shown).
D6 درجة الثقة = uncalibrated threat confidence 0–100 = max(model, fusion); bands `min(4, floor(score/20))`; UI says "درجة (غير معايرة)".
D7 الخطورة = decision-contract triage class — the sorting axis, never derived from the score.
D8 windows: range closed `[now−d, now]`; previous half-open `[now−2d, now−d)` (brush-shifted variant closed); timeline bucket `k` half-open `[from+size·k, from+size·(k+1))`, last closed at `now`; brush closed `[buckets[s].from, buckets[e].to]`; hero ribbon `[now−30min, now]`; heat strip `[now−30min, now)`; all epoch-ms arithmetic (DST-safe).
D9 session scope: counts are over alerts received this session, buffered at 50 newest; partial coverage is labeled and previous-window deltas suppressed when `oldestObserved > baselineWindow.from`.
Industry semantics reference (not a benchmark): WT-04 C-D1 flow (pass-through events over a period) vs occupancy (present now) matches D3/D4; vendor accuracy numbers are account-gated and NOT cited.

## 6. Validation summary (full command outputs in the handoff)

- `node --test lib/__tests__/sentinel-selectors-stats.test.mjs` — 15 pass (composition, denominators, brush parity, cap coverage, band edges, DST fall-back/spring-forward).
- `node --test components/overview/overview-time.test.mjs` — 9 pass (window math, step counts, boundary semantics, DST).
- `py -3.14 -m pytest backend/tests/test_stats_service.py -q` — 12 pass (windows, camera scope, denominators, previous window, validation, integrity failure state, viewer role).
- `py -3.14 -m py_compile backend/api.py backend/stats_service.py` — OK.
- `npm run docs:sync` — regenerated CURRENT/DESIGN/SOURCE-MANIFEST/design-preview/design-tokens after the token change; `npm run docs:check` shows exactly the SC-9 expected line: `Unregistered active document: docs/campaign/engineering/26-stats-semantics.md`.
- typecheck / lint / browser smoke — see handoff (post-`npm ci`).

## 7. Known limitations

1. `/stats/overview` undercounts by construction (alerts without evidence artifacts are absent); the payload
   and UI label the scope "سجل الأدلة" everywhere it is shown. A true alert history requires a persisted alert
   store (currently nonexistent — `alert_detected` audit rows exist only in a historical `audit_logs.jsonl`).
2. Persisted mode offers no drill-through to historical events (the incidents view is session-only); labeled in UI.
3. The brush window cannot travel through CrossFilters (see §4).
4. `lib/dashboard-data.ts` remains dead fabricated demo data outside S-13 (flagged to the integrator, G-7).
5. Light-theme visual verification and NVDA screen-reader pass are [UNVERIFIED — browser/AT] beyond the measured contrast ratios.
