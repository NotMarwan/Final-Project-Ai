---
authority: scoped
non_authoritative: true
---

# WT-26 — Statistics semantics audit (Phase A): what every dashboard number means

**Ticket:** WT-26 (statistics and dashboard correctness), slice S-13.
**Worktree:** `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-26`, branch `codex/sentinel-26-stats`, pinned baseline
`e86d34b5d16abcc133ad3470c8d135d00b2423d4` (`final-demo-transfer`).
**Scope:** `components/overview/**`, `lib/detection-types.ts` label/colour maps, additive `lib/sentinel-selectors.ts`.
This document is a scoped engineering audit — it is **not** status or design authority. Every statement below is grounded in
the pinned-baseline source at the cited `file:line`. Inferences are tagged `[INFERENCE]`.
Research basis: WT-11 `docs/campaign/research/11-webapp-analytics.md` §2, §6 (S26-1…S26-9), §7, §8.

---

## 1. Vocabulary discipline (S26-1): event ≠ detection ≠ alert ≠ incident

These words are used loosely in the current UI. The precise meanings that follow from the code:

| Term | Arabic UI term today | What it actually is in this codebase | Where |
|---|---|---|---|
| **Event (generic)** | "حدث" | Anything that happened on the system (camera disconnect, motion…). No counter exists for generic events. | — |
| **Detection / model read** | "رصد" (e.g. "رصد سلاح") | One per-frame model output (violence score, weapon score, person box). These exist only as *latest-frame telemetry* (`PipelineTelemetry` / `DetectionOverlayEnvelope`) and are **never counted** in the overview. | `lib/detection-envelope.ts:11-16`, `lib/pipeline-telemetry.ts` |
| **Alert** | "تنبيه" | One confirmed decision-contract decision published on SSE `/alerts`, with a unique `id`. This is the **counting unit of every overview statistic**. `parseAlertEnvelope` validates and normalizes it. | `lib/sentinel-selectors.ts:45-104`, `backend/api.py:940-997` |
| **Notification** | (toast) | Delivery of an alert to the operator (Telegram / in-app toast). Delivery state is **not** counted anywhere in the overview. | `backend/notifications.py`, `components/alert-toast.tsx` |
| **Incident** | "حادث/حادثة" | Operator-triage construct (investigation dossier on an alert). There is **no incident entity, no incident counter, no incident store** — the overview uses "حوادث" as a synonym for alerts. | `app/page.tsx:100`, `components/overview/overview.tsx:158` |

**Confidence ≠ severity ≠ accuracy.**

- `confidence` on a `LiveAlert` is the backend's **threat confidence** `threat_conf = max(model_conf, fusion score)` on a 0–100
  scale (`backend/api.py:935-943`). It is an **uncalibrated score**, not a probability and not an accuracy. The calibration
  artifact is absent (`calibrationStatus: "unverified"`, F-40) — no accuracy/precision/recall number may be displayed.
- `calibratedConfidence` / `calibrated_probability` exist in the payload but the frontend contract drops them
  (`parseAlertEnvelope` never copies them) — the histogram therefore shows **threat-confidence bands only**.
- `severity` ∈ {critical, high, medium} is the decision contract's **triage axis** and is what the operator should sort on.
- Frontend validator silently rejects `severity: "none"` and any confidence outside 0–100 (`lib/sentinel-selectors.ts:49-51,55-59`).

---

## 2. Data sources and denominators

### 2.1 The only complete alert source for the UI is a ≤50-alert in-memory session buffer

`lib/sentinel-store.tsx:34` — `alerts: [action.alert, ...state.alerts].slice(0, 50)` (newest first, deduplicated by `id` at
`lib/sentinel-store.tsx:32`). Alerts are received live over SSE `/alerts` (`lib/sentinel-store.tsx:64-98`) or replaced wholesale
by fixtures in `?fixtures=1` mode (`lib/ui-fixtures.ts`).

Consequences (gap G-6/G-10):

- Any count over the buffer is a **session-scoped count of received alerts**, not a historical total. Nothing before page load
  or beyond the newest 50 alerts is observable. The overview footnote says this (`overview.tsx:159`) but individual numbers do not.
- The "all" range (`كل الجلسة`) is therefore *session span*, capped by both session start and the 50-alert eviction — not "all time".
- A previous-window delta is only honest when the previous window is fully inside the observed span; see §4.1.

### 2.2 Persisted sources on the backend — and what they can/cannot denominat

| Source | Written when | Fields relevant to stats | Usable as alert denominator? |
|---|---|---|---|
| `evidence_ledger.jsonl` (hash-chained; `backend/evidence.py:55-57,117-175`) | only when an evidence clip finishes (`backend/api.py:785-792`) **or** a report PDF is generated/downloaded (`backend/api.py:2049-2055`) | `timestamp` (**evidence-write time**, UTC `datetime.now()` — not alert occurrence time), `alertId`, `cameraId`, `severity`, `confidence`, `fusionScore`, `motionScore`, `weaponScore`, face counts, asset SHA-256s | **No** — it counts *alerts that received evidence artifacts*. It is a valid denominator for "evidence coverage", never for "alerts that happened". |
| `backend/audit_logs.jsonl` (`backend/security.py:105-120`) | every audited action (`set_threshold`, `evidence_clip_ready`, `report_download`, …) | `timestamp`, `action`, `alertId`, `details` | **No** — the pinned baseline writes **no `alert_detected` action** (verified: no such call in `backend/**/*.py`). The on-disk file contains April-2026 `alert_detected` rows from an older build only. |
| `GET /system/metrics` | never populated (runtime-map F-38) | zeros | **No** — must never be a denominator (WT-11 §8.8). |
| `GET /cameras/status`, `GET /system/status` | live state | camera online state | The right denominator source for **coverage** (= observed camera-time / window) — currently consumed by no frontend caller (G-3, F-36/F-38). Until consumed, coverage displays "غير متاح", not 0 %. |

`[INFERENCE]` Phase B plan: one additive stats route aggregating `evidence_ledger.jsonl` with explicit window + camera scope is
justified *only* under the label "سجل الأدلة" (evidence-record scope: `evidenceWriteTime`, "alerts with generated evidence").
It must ship with graceful fallback to session data labeled "نطاق الجلسة".

### 2.3 Person counts: two different quantities, one of which does not exist

- **Visible persons (now)** — `personCount` on the latest `person_detection` / detection-overlay frame
  (`lib/sentinel-selectors.ts:105-110`, `lib/detection-envelope.ts:131-133`). It is an **instantaneous frame count** with no time
  window. Displayed in the monitor player (`components/video-player.tsx:184`), not in the overview.
- **Tracked-unique persons over a period** — distinct track IDs within a window. The backend sends per-frame `trackIds`
  (`backend/api.py:478`) but **no store persists or aggregates them**. This quantity is **not computable** from any registered
  source. The UI must show it as unavailable with the reason, never as 0 and never estimated. `[INFERENCE]`
- `parsePersonCountEnvelope` messages must never increment alert counts (S26-1 verification) — current code already routes them
  to a separate `person` action (`lib/sentinel-store.tsx:87-92`); keep a test for it.

---

## 3. Exact meaning of every number currently on the overview

Notation: `now` = `max(clock tick, newest alert isoTime)` (`overview.tsx:89`; tick `NOW_TICK_MS = 15 s`, `overview.tsx:17`),
`d` = range duration (`15m`/`1h`/`24h`), `visible` = alerts passing **range ∩ cameraId ∩ type ∩ severity ∩ confidenceBand ∩ customBrush**
(`overview.tsx:92-94`, `lib/sentinel-selectors.ts:112-121`).

### 3.1 Hero

| UI element | Counts | Window | Filters | Notes / pitfalls |
|---|---|---|---|---|
| Gauge "مستوى التنبيهات" (`حرج/مرتفع/هادئ`) | max severity present | last **15 min** | **none** — ignores every active filter (`overview.tsx:117-119`) | A "مرتفع" gauge can coexist with an empty filtered dashboard. Must be labeled as an unfiltered 15-minute signal. |
| Hero ribbon "X تنبيه مستلم" | alerts received | last **30 min** (`RIBBON_DURATION_MS`, `hero-incident-instrument.tsx:7`) | all filters **except cameraId** (`heroAlerts`, `overview.tsx:90`) | Top-3 cameras shown (`shown = cameraIds.slice(0, 3)`), remainder summarized as "+N كاميرات أخرى". |
| Ribbon event click | — | event window ± **2.5 min** (`EVENT_WINDOW_MS`, `hero-incident-instrument.tsx:8`) clamped to the ribbon | sets `cameraId` + brush | The 2.5-minute window is arbitrary presentation, not a decision-contract duration. |

### 3.2 Stat cards ("مؤشرات الفترة")

| Card | Counts (denominator) | Window | Comparison delta |
|---|---|---|---|
| "تنبيهات الفترة" | alert count in `visible` | closed `[now-d, now]` (`selectVisibleAlerts`, cutoff `now-d`) + brush | `previousWindowCount` over `[now-2d, now-d)` half-open (`lib/sentinel-selectors.ts:185-203`) |
| "حرجة" | alerts with `severity = critical` in `visible` | same | previous window over pre-filtered critical alerts (`overview.tsx:113`) |
| "أسلحة" / "اعتداءات" | alerts with `type = Weapon` / `Violence` in `visible` — **alert counts, not detection counts, not weapon-label counts** | same | `overview.tsx:114-115` |
| "زمن التنبيه p50 / p95" | percentiles of `alertLatencyMs` samples in `visible`; **≥ 2 samples or both are `null`** (`MIN_LATENCY_SAMPLES`, `lib/sentinel-selectors.ts:22,137-142`) | same | none |
| "الكاميرات النشطة" | **"غير متاح"** — honest hardcoded absence (G-3) | — | — |

**Latency semantics (important):** `alertLatencyMs = round((perf_counter() - t0) * 1000, 1)` measured while building the alert
payload (`backend/api.py:964`) — i.e. **server-side decision-computation latency**, in no way "glass-to-alert" (measurement
rules: exposure→display timestamp domains must not be subtracted). The streaming snapshot path sends `alertLatencyMs: None`
(`backend/pipeline_render.py:228`), so its alerts are **silently excluded** from the percentile samples. The card label
"زمن التنبيه" (alert latency) implies delivery latency — misleading. Percentile method: linear interpolation on the sorted
samples at index `(n-1)·f`, rounded (`lib/sentinel-selectors.ts:134-140`). The sparkline plots the **last ≤ 8 samples only**
(`overview.tsx:132`).

### 3.3 Deltas ("عن الفترة السابقة") — three honesty problems

`deltaLabel` (`overview.tsx:66-70`) is computed from `previousWindowCount`:

1. **Brush mismatch:** the current count includes the custom brush (`customWindow`) but the previous count does **not**
   (`overview.tsx:112` calls `previousWindowCount(alerts, …)` with no brush). A brushed view compares apples to oranges.
2. **Coverage blindness (S26-3d):** the delta is drawn even when the previous window is only partially observed — session
   started mid-window or the 50-alert cap evicted the older part. It must be suppressed (or labeled) whenever
   `oldestObservedTime > previousWindow.from`.
3. `range = "all"` correctly returns `null` → "لا توجد فترة مقارنة" (`lib/sentinel-selectors.ts:186`).

### 3.4 Charts (cross-filter isolation matrix)

Each chart deliberately drops **its own** dimension so the distribution stays readable while other filters apply
(`overview.tsx:95-105`):

| Chart | Data set | Drops | Applies | Brush? |
|---|---|---|---|---|
| "تسلسل الحوادث" (timeline) | `chartDimensions.timeline` | `cameraId`, `type` | range, severity, confidenceBand | **No** — plotted data ignores the brush so the brush stays legible over a stable chart (`overview.tsx:103`) |
| "حسب الكاميرا" | `camera` | `cameraId` | range, type, severity, confidenceBand | Yes |
| "توزيع الخطورة" (donut) | `severity` | `severity` | range, cameraId, type, confidenceBand | Yes |
| "توزيع الثقة" (histogram) | `confidence` | `confidenceBand` | range, cameraId, type, severity | Yes |
| (empty-state probe) | `context` | everything but range | range | No (`overview.tsx:104`) |

- Donut centre number = `severityAlerts.length` = alerts matching all filters **except severity** + brush — a set-size, not
  "all alerts". Label says "تنبيه" (correct unit).
- Camera rows list **only cameras that produced ≥ 1 matching alert**; zero-alert cameras are absent (not shown as 0) —
  the denominator of "which cameras" is therefore undefined unless `/cameras/status` is consumed (§2.2).
- Timeline buckets: 5 / 6 / 8 equal steps for `15m` / `1h` / (`24h` ∪ `all`), duration `d` for fixed ranges and
  `max(1h, now - oldest + 1)` for `all` (`components/overview/overview-time.ts:5-6,13-35`; a second, near-duplicate engine lives
  in `lib/sentinel-selectors.ts:153-172` `timeBuckets` and feeds only the stat-card sparklines — **two bucket engines is itself
  a drift risk**).
- Bucket `k` = `[from + size·k, from + size·(k+1))`, except the last bucket is closed at `now` (`Math.min(count-1, …)`).
  `windowForBuckets(first,last)` returns the **closed** `[buckets[start].from, buckets[end].to]`
  (`overview-time.ts:37-41`), so an alert stamped exactly on an interior bucket boundary draws in the later bucket but is
  included by either neighbouring brush. `[INFERENCE]` Boundary-overlap is ±0 ms and only affects exact-timestamp collisions;
  it must be covered by tests and documented, not silently "fixed" by shifting windows.

### 3.5 Confidence histogram

- Band mapping: `min(4, floor(confidence / 20))` → bands `0–20, 20–40, 40–60, 60–80, 80–100`
  (`lib/sentinel-selectors.ts:174-183`, filter side `:120,202`). The last band absorbs everything ≥ 80 including 100.
- The score behind the bands is **threat confidence** (§1), uncalibrated. The chip label `الثقة X–Y%` and the chart caption
  "نسب الثقة المبلّغ عنها" must say "درجة (غير معايرة)" (S26-6) to avoid reading as accuracy/probability.
- Alerts with confidence outside 0–100 are dropped silently by the histogram — unreachable in practice because
  `parseAlertEnvelope` rejects them (`lib/sentinel-selectors.ts:55`).

### 3.6 `minuteHeatBuckets` (30-minute strip; `lib/detection-types.ts:79-101`)

Used by the alert-history panel (`components/alert-history.tsx:44`) and its tests (`hooks/__tests__/alert-feed.test.mjs:25`),
not by the overview. Semantics: `count` one-minute buckets (default 30, clamped 1..120), bucket `k` =
`[start + k·60 s, start + (k+1)·60 s)`, `start = now − count·60 s`; an alert at exactly `time = now` falls in index `count`
and is **excluded** — the strip covers `[now−30 min, now)`. `total` counts alerts, `critical` counts severity-critical alerts.

### 3.7 "أحدث الحوادث" list

`visible.slice(0, 5)` (`overview.tsx:158`) — the 5 newest **alerts** matching the current filters+brush, titled "أحدث الحوادث"
(latest *incidents*) with row labels "رصد سلاح"/"رصد اعتداء" (*detection* wording). Both labels misname the unit (§1).

---

## 4. Misleading-label inventory and required corrections

| # | Where | Problem | Correction | Track |
|---|---|---|---|---|
| C-1 | `overview-charts.tsx` panel title "تسلسل الحوادث"; `overview.tsx` "أحدث الحوادث" | alerts presented as incidents | rename to "تسلسل التنبيهات" / "أحدث التنبيهات"; keep "حادثة" only for the triage dossier | S26-1 |
| C-2 | `overview.tsx:158` rows "رصد سلاح/رصد اعطھط¯ط§ط،" | detection wording on alert rows | "تنبيه سلاح" / "تنبيه اعتداء" | S26-1 |
| C-3 | `overview.tsx:153` "زمن التنبيه" | implies alert delivery; measures server decision computation (`api.py:964`); streaming alerts carry `None` and are silently excluded | relabel "زمن احتساب القرار (خادم)" + note "ليس زمن الوصول" + show sample count `n` next to p50/p95 | S26-1, measurement rules |
| C-4 | `overview.tsx:149-152` delta captions | brush mismatch (§3.3.1) + coverage blindness (§3.3.2) | compute delta over the same brushed set; suppress with "الفترة السابقة خارج نطاق الجلسة" when `oldestObserved > prevWindow.from` | S26-3 |
| C-5 | `overview.tsx:22` `all: "كل الجلسة"` | hides the 50-alert cap and session start | "الجلسة (حد أقصى 50)" + render `windowStart–windowEnd` + session-start stamp next to counts | S26-3 |
| C-6 | gauge `overview.tsx:117-119` | unfiltered 15-min signal presented next to filtered stats | label the gauge "إشارة آخر 15 دقيقة (بلا تصفية)" or apply filters — decision recorded in Phase B | S26-1 |
| C-7 | confidence chip/caption | "الثقة %" reads as probability/accuracy | "درجة (غير معايرة)" + keep severity as triage axis | S26-6 |
| C-8 | person quantities (§2.3) | one number "الأشخاص" for a frame gauge; tracked-unique silently nonexistent | definitions legend: "أشخاص ظاهرون (الإطار الأخير)"; "متابَعون فريدون: غير متاح — لا يوجد مصدر يوفّر العدد" | S26-1 |
| C-9 | label-map duplication | `SEVERITY_LABEL` copied in `overview.tsx:23`, `overview-charts.tsx:12`, `hero-incident-instrument.tsx:10`; `TYPE_LABEL`/`SEVERITY_COLOR` in `overview-charts.tsx:11-14`; `CATEGORY_LABELS` in `lib/detection-types.ts:38-45`; alert-feed/history each carry their own maps | consolidate slice-owned maps into `lib/detection-types.ts` and import; flag remaining copies for the integrator | ui-contract drift note |
| C-10 | two bucket engines (`overview-time.ts` vs `sentinel-selectors.ts#timeBuckets`) | same step counts (5/6/8) but separate implementations and different label locales | keep `overview-time.ts` as the single window/bucket source for the overview; sparklines migrate or get parity tests | drift |
| C-11 | `app/manifest.ts` theme-color `#0f172a` | differs from surface-0 `#090c0e` (G-8) | set theme-color to the surface-0 token value | Phase B (gated) |
| C-12 | `--threat-medium` = `--state-stale` (same hex `#93aaa6`/`#52635e`, `app/globals.css:21,26,98,103`) | "medium severity" and "stale source" are visually identical (G-5) | give `--state-stale` its own token value, or never encode either state by colour alone (explicit labels already exist for source state) | Phase B (gated; token change needs design-authority rules + `docs:sync`) |
| C-13 | `lib/dashboard-data.ts` | hardcoded fabricated demo alerts ("Physical Assault", confidence 96) with **zero importers** | delete or quarantine; out of S-13 slice — flagged to the integrator | drift/manifest |
| C-14 | empty/zero/stale per chart | the three-way distinction (no data / zero / stale) exists only in the feed (S26-8) | chart headers get freshness + distinct empty states | Phase B |
| C-15 | no click-through from stats (S26-4) | every statistic must link to its filtered events | stat/segment click → apply CrossFilters → incidents view with first matching alert selected (in-page state until G-1 routes exist) | Phase B |

## 5. Counting-semantics definitions (canonical; to be labeled in the UI)

- **D1 — تنبيه (alert):** one confirmed decision-contract decision published on SSE `/alerts` with a unique id. **Unit of every
  overview number.** Duplicates are dropped by id.
- **D2 — كشف (detection / model read):** one per-frame model output. Never counted in the overview; telemetry only.
- **D3 — أشخاص ظاهرون (visible persons, now):** person count of the latest processed frame — instantaneous, no window.
- **D4 — أشخاص متبَّعون فريدون خلال الفترة (tracked-unique persons, window):** distinct track ids in the window —
  **not supplied by any registered source; displayed as unavailable with this reason.**
- **D5 — زمن احتساب القرار:** server-side payload-build latency (perf_counter) — never "glass-to-alert".
- **D6 — درجة الثقة (score):** threat confidence 0–100 = max(model score, fusion score), **uncalibrated**
  (`calibrationStatus: "unverified"`). Bands `min(4, floor(score/20))`.
- **D7 — الخطورة (severity):** decision-contract triage class critical/high/medium. Not derivable from the score.
- **D8 — windows:** range window closed `[now−d, now]`; previous comparison window half-open `[now−2d, now−d)`; timeline
  bucket `k` half-open `[from+size·k, from+size·(k+1))` with last bucket closed at `now`; brush windows closed
  `[buckets[start].from, buckets[end].to]`; hero ribbon `[now−30 min, now]`; heat strip `[now−30 min, now)`. All arithmetic is
  epoch-milliseconds — timezone/DST independent; wall-clock strings are display-only (locale `ar-SA`/`formatTime24`).
- **D9 — session scope:** every count is over alerts **received in this browser session**, buffered at 50 newest. When the
  buffer is capped or the session started inside the window, partial coverage must be labeled, and previous-window deltas
  suppressed (C-4/C-5).

## 6. Verification performed in Phase A (read-only)

- `lib/sentinel-store.tsx` reducer read in full: cap = 50, dedupe by id, fixtures replace the buffer.
- `backend/evidence.py` + `backend/api.py` append sites read: ledger timestamps = evidence-write time; no `alert_detected`
  audit call exists in the pinned baseline (grep over `backend/**/*.py`).
- `backend/audit_logs.jsonl` (primary repo) sampled: historical `alert_detected` rows exist (April 2026 build) but cannot be
  treated as a complete store.
- No accuracy/calibration artifact: `backend/model_calibration.json` absent (consistent with WT-11 §8.6, F-40).

## 7. Limitations

- All UI-string claims were read from source, not rendered in a browser (no browser pass in Phase A).
- `formatTime24` / `toLocaleTimeString("ar-SA")` outputs not asserted; locale rendering may vary with ICU builds.
- Whether the evidence ledger is actually written during a live run was not measured here (no GPU/camera run in Phase A).

## 8. Correction status after Phase B (commits 07f18bb, e687b96, 0310cbb, d082150)

| Correction | Status |
|---|---|
| C-1 alert-not-incident wording | DONE — "تسلسل التنبيهات" / "أحدث التنبيهات" |
| C-2 alert row labels | DONE — "تنبيه سلاح" / "تنبيه اعتداء" (ALERT_TYPE_LABELS) |
| C-3 latency label + sample count | DONE — "زمن احتساب القرار (خادم)" + "ليس زمن الوصول" + n |
| C-4 delta honesty | DONE — brush parity (shifted window) + coverage suppression + reason labels (tested) |
| C-5 `all` cap visibility | DONE — "الجلسة (حد أقصى 50)" + window bounds + session-start stamp + cap warning |
| C-6 gauge scope | DONE — "إشارة آخر 15 دقيقة — بلا تصفية" |
| C-7 confidence wording | DONE — "درجة (غير معايرة)" chip/caption; histogram caption states 0–100 uncalibrated |
| C-8 person quantities | DONE — STATS_LEGEND D3/D4 definitions; tracked-unique explicitly unavailable |
| C-9 label-map duplication | DONE for S-13 maps (detection-types authority); remaining copies in alert-feed/history/geo-dashboard flagged to integrator |
| C-10 duplicate bucket engines | PARTIAL — both engines kept; `overview-time.ts` tested (DST/boundaries); `timeBuckets` still feeds sparklines only (follow-up: migrate or parity-test) |
| C-11 manifest drift (G-8) | DONE — `#090c0e` (surface-0) |
| C-12 stale/medium collision (G-5) | DONE — `--state-stale` distinct in both themes (measured contrast: 8.76:1 dark, 6.23:1 light) |
| C-13 dead `lib/dashboard-data.ts` | NOT DONE — outside S-13 ownership (flagged to integrator) |
| C-14 three-way empty/zero/stale per chart | PARTIAL — per-chart text summaries + data tables + scope note; per-chart offline/stale empty states remain open |
| C-15 stat drill-through | DONE for session scope (CrossFilters + first matching alert); persisted scope labeled as non-drillable |
| Session cap / G-10 | PARTIAL — labeled + delta-suppressed; historical restore needs a history API (new work) |
| Persisted analytics / G-6-G-10 source | DONE — `GET /stats/overview` (evidence-record scope, labeled) + graceful labeled fallback |
