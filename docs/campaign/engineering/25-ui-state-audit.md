---
authority: scoped
non_authoritative: true
---

# WT-25 — Operator interface & alerts: state audit (Phase A)

**Ticket:** WT-25 (slice S-11 incidents UI: `alert-feed`, `alert-history`, `alert-toast`, `clip-sidebar`, `clip-player`, `incident-replay`, `incident-panel`).
**Worktree:** `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-25`, branch `codex/sentinel-25-ui-alerts`, pinned baseline `e86d34b5d16abcc133ad3470c8d135d00b2423d4`.
**Method:** static source reading of the committed tree at the pinned baseline (no browser session, no backend run). Every claim carries `path:line`. Where the backend is traced, `backend/api.py` is read only.
**Scope boundary:** `components/category-filter.tsx`, `components/sections/incidents-section.tsx`, `components/shell/**`, `app/page.tsx`, `components/overview/**` are owned by other slices (S-10/S-13, ownership-map §1) and are described here as *unchanged context*, not as work items.
**Blueprint inputs read:** `docs/blueprint/design-map.md`, `docs/blueprint/ui-contract.md` (WT-02), `docs/blueprint/runtime-map.md`, `docs/blueprint/ownership-map.md` (WT-01), reconciled seed `docs/blueprint/INDEX.md`/`index.json` (WT-03, commit 27c18d2), WT-11 research §5 (`11-webapp-analytics.md`).

---

## 1. Control inventory (what each control does, where it lands, how it fails)

### 1.1 `components/alert-feed.tsx` (106 lines) — the received-alerts queue (U-04 left column)

| Control | Site | Action → landing | Failure / disconnect / stale behavior |
|---|---|---|---|
| Received count badge | `:72` | renders `alerts.length` (already filtered upstream); `aria-label="{n} تنبيه"` | none (display only) |
| Category chips | `:74` → `components/category-filter.tsx` | `onCategoryChange` → `app/page.tsx:88` `setFilters({…, type})` (Weapon/Violence) | none; counts at `:38-45` recompute `selectVisibleAlerts` with `type: undefined` |
| Alert row | `:91` | `onSelectAlert(alert)` → `sentinel-store.tsx:125` `dispatch("select")` → `selectedAlert` | selection persists across disconnect (no reset on `connection` action, `sentinel-store.tsx:43`) |
| Row keyboard nav | `:62-65` | ArrowUp/Down/Home/End → `focusIndex` (`:52-60`): page + `focus()` + `scrollIntoView` | inert when `alerts.length === 0` |
| Camera chip | `:96` | `setFilters({…, cameraId})` toggle, `aria-pressed` | none |
| Row provenance badge | `:97` | `إعادة تشغيل` if `cameraId.startsWith("EXAMPLE-")`; `عينة` if `fixtureMode`; else `مستلم` | heuristic, not the `SourceVisualState` contract (drift, §4 D-7) |
| Confidence bar | `:98` | bar width `clamp(confidence)%`, `title="ثقة التنبيه {n}%"` | shows a bare percentage; no scale/calibration label (drift, §4 D-2) |
| Pagination | `:103` | `WINDOW_SIZE = 80` (`:19`); prev/next; disabled at edges | none |
| Footer provenance | `:104` | fixture / online / unknown copy — camera state explicitly marked unverified | honest; no camera-presence endpoint consumed (G-3) |
| Empty states | `:76-80` | three distinct: filtered-empty (+clear), channel-offline, nothing-in-window | `connectionStatus === "offline" && !fixtureMode` selects the offline copy |
| Fresh-entry motion | `:89-90` | index 0 and `isoTime` within 10 s → `motion-safe:animate-slide-from-right` | reduced-motion respected via `motion-safe:` |

**Failure gap:** the feed has no error state of its own. SSE errors only surface as `connectionStatus` (`sentinel-store.tsx:98-113`); malformed envelopes are swallowed by `catch { /* Ignore malformed envelopes. */ }` (`sentinel-store.tsx:96`) — a silent drop (D-10).

### 1.2 `components/alert-history.tsx` (80 lines) — session history + 30-minute distribution

| Control | Site | Action → landing | Failure behavior |
|---|---|---|---|
| Compact 30-min strip | `:53-59` | `minuteHeatBuckets(alerts, now, 30)` (`lib/detection-types.ts`) | `role="img"` + aria-label; no error state (pure props) |
| Stats toggle | `:62` | `aria-expanded` → 4-cell grid `:66` (total/critical/high/medium) | none |
| Minute histogram | `:63-65` | per-bucket `title` tooltips | none |
| Search | `:67` | local filter over `id/cameraId/location` (`:40-43`) | "لا نتائج لهذا البحث" empty copy `:68` |
| Sort group | `:67` | newest/oldest `aria-pressed`; `:43` sorts by `Date.parse(isoTime)` | invalid times sort to `NaN` (stable order not guaranteed) |
| Row select / expand | `:74` | select → `onSelectAlert`; expand → `expandedId` → detail grid `:75` (id, time, fusion/motion/weapon/threat scores, personCount, labels, reason) | none |
| Clip download (expanded) | `:75` with `clipDownloadUrl` `:19-25`, `downloadApiFile` `:6` | same-origin-guarded URL → `downloadApiFile` | `downloadError` state `:38`; download only when `alert.clipUrl && !privacyMode` |
| Clock | `:39` | `now` frozen at mount | relative times do not tick during a long session (D-8) |

### 1.3 `components/alert-toast.tsx` (48 lines) — single-slot alert toast

| Control | Site | Action → landing | Failure behavior |
|---|---|---|---|
| Suppression | `:18`, `:26`, `:32` | `isToastSuppressedForTab(activeTab)` (`lib/live-visual-state.ts`) → dismiss + render `null` | suppression dismisses immediately, so no toast is lost silently |
| Auto-dismiss | `:24-30` | non-critical 6 s timer; critical persists | timer cleared on unmount |
| Dismiss | `:43` | `onDismiss` → `app/page.tsx:92` `setToastAlert(null)` | none |
| Review | `:45` | `onNavigate` → `app/page.tsx:92` `selectIncident(toastAlert)` + clear | works only for the newest alert (single slot, D-5) |
| ARIA | `:38` | critical: `role="alert" aria-live="assertive"`; otherwise `role="status" aria-live="polite"`; `aria-atomic` | matches the ARIA APG alert pattern |
| Copy | `:35-36`, `:42` | inline severity label/color ternary (drift, D-1); `ثقة التنبيه {n}%` + `حالة المصدر تحتاج تحققاً مستقلاً` | honest source caveat |
| Motion | `:38`, `:41` | `motion-safe:animate-alert-enter`, `motion-safe:animate-pulse` | reduced-motion respected |

**Note:** a newer alert replaces the visible one (`app/page.tsx:57-60` sets `toastAlert`), so concurrent alerts are not stacked (D-5). The generic shadcn toast system (`components/ui/toaster.tsx`, `components/ui/sonner.tsx`, `hooks/use-toast.ts`) is never mounted in `app/` — unused (D-12).

### 1.4 `components/clip-sidebar.tsx` (165 lines) — related clips + modal replay

| Control | Site | Action → landing | Failure behavior |
|---|---|---|---|
| Clip polling | `:100-105` | `GET /api/clips/list` every 5 s while `connectionStatus === "online" && !fixtureMode` | `status` union `:69`; on throw → `error` (`:98`) + retry button `:138` |
| Response parse | `:38-55` | strict: `alertId` `/^[A-Za-z0-9_-]{1,128}$/`, `clipUrl === "/clips/" + alertId`, finite `size`/`mtime` ≥ 0, severity whitelist | malformed rows are dropped per-item (`flatMap`), not fatal |
| Related filter | `:74-89` | cross-filter aware (`cameraId/type/severity/confidenceBand/range`) + relatedness to the selected alert | none |
| Refresh | `:132` | `fetchClips`; disabled in fixture mode | none |
| Clip card | `:143` | `onSelectAlert(alert)` when present + open modal | none |
| Modal | `:151-159` | `role="dialog" aria-modal`, Escape close `:106-111`, `autoFocus` on close `:153`, privacy mask `:154`, else `IncidentReplay` `:155` | no focus trap and no focus restoration (D-9) |
| Download | `:112-129` | `GET /clips/{id}` → blob → anchor download; revoke after 5 s | `downloadBusy`/`downloadError` `:71-72`; error alert `:157` `role="alert"` |
| Empty states | `:136-139` | fixture / loading / error / no-related — four distinct copies | honest |

### 1.5 `components/clip-player.tsx` (24 lines) — generic clip playback

| Control | Site | Action → landing | Failure behavior |
|---|---|---|---|
| Play/pause, loop, speed, fullscreen | `:22` | `useClipPlayback` hook; loop `aria-pressed`; speed `Slider` labelled `clip-speed` | controls disabled when `!clipUrl || failed` |
| Source sync | `:14-18` | `playClip(clipUrl)` or direct `src` assignment | `onError` → `failed` `:12` → `VideoOff` + "تعذّر تشغيل المقطع"; no clip → "لا يوجد مقطع محدد" `:21` |
| src comparison | `:17` | `videoRef.current.src !== clipUrl` (absolute vs relative risk) | may re-assign identity; benign but fragile |

### 1.6 `components/incident-replay.tsx` (168 lines) — recorded-evidence viewer

| Control | Site | Action → landing | Failure behavior |
|---|---|---|---|
| Evidence fetch | `:58-85` | `GET /clips/{id}` via `apiFetch`; 404 → auto-retry ×10 @2 s (`:68-70`, `MAX_AUTO_RETRIES`/`RETRY_MS` `:10-11`) | status union `:12`; `error` → retry button `:139`; `unavailable` → "لا يوجد مقطع دليل" |
| Status callback | `:57` | `onStatusChange(status)` → parent `incident-panel.tsx:211` `setReplayStatus` | drives the evidence-log row `:221` |
| Replay/provenance badge | `:113` | always `دليل مسجل · ليس بثاً حياً` | **never renders a live label** (verified in source) |
| Transport | `:143-149` | play/pause, restart, scrub (`dir="ltr"`, aria-label), mute, fullscreen | all disabled unless `status === "ready"` |
| Detection marker / overlay | `:135`, `:129-131` | marker at `detectionOffsetSeconds/duration`; `threatBoxes` projected within ±0.7 s (`:126-128`) | marker absent when offset unknown; footer says so `:163` |
| Status overlay | `:132-140` | loading spinner (`motion-reduce:animate-none`), error, unavailable | `role="status"` |
| Meta footer | `:162-164` | threat type + confidence % + location + timestamp; `غير متوفر` fallbacks | bare confidence percentage, no calibration label (D-2) |

### 1.7 `components/incident-panel.tsx` (263 lines) — the incident dossier (U-04 centre column)

| Control | Site | Action → landing | Failure behavior |
|---|---|---|---|
| Empty state | `:187` | "اختر تنبيهاً لفتح ملف الحادثة" | none |
| Severity chip | `:194` | toggles the cross-filter severity (`setFilter`) via `onFiltersChange` | none |
| Fixture / offline banners | `:196`, `:197` | fixture: sample-only; offline: "قد تكون بيانات هذه الحادثة قديمة" | honest staleness copy |
| Facts grid | `:199-202` | camera (filter toggle), location, alert time, **latency** (`كمون التنبيه`) | `latencyLabel` = `غير متوفر` when `alertLatencyMs` absent (`:79-80`) — unmeasured latency is unavailable, not 0 |
| Category chip | `:204` | toggles `filters.type` | none |
| Evidence region | `:207-211` | fixture / privacy / offline / `IncidentReplay` | three distinct non-playback states |
| Metrics | `:216-218` | fusion / weapon / motion bars (`null` → `غير متوفر`) | bar width uses `value ?? 0` (`:47`) — 0-width with the unavailable label |
| Confidence disclaimer | `:217` | "لا تعني هذه النسبة دقة النظام" | correct discipline |
| Evidence-chain panel | `:219-224`, fetch `:120-135` | `GET /evidence_chain/{id}` → `parseEvidenceChainRecord` (`lib/local-report.ts:33`) | 404 → `unavailable` ("لم توفر الخدمة قيداً"); invalid record → `error`; refresh `:220` |
| Weapon labels / face summary | `:230`, `:233-236` | from alert payload; privacy-masked | absent → `غير متوفر` |
| Download evidence | `:243` | `downloadEvidence` `:137-148`: `GET /download_evidence/{id}`, **202 → poll ×20 @1.5 s**, blob save | error message `:159` "تحقق من خدمة الأدلة وحاول مجدداً" |
| Download PDF | `:244` | `GET /download_report/{id}` | error message `:159` |
| Escalation review | `:245`, dialog `:259-261` | honest dead end: "لا توجد خدمة إرسال فريق أمني مرتبطة بهذا الزر" | `fixtureMode` disables it |
| False-positive review | `:246` | honest dead end: message "لا توجد واجهة لحفظ حكم الإنذار الكاذب" | no persistence |
| Alert policy sliders | `:253-257` | `POST /set_threshold` (`{threshold: value/100}`) and `POST /set_cooldown`; debounce 400 ms `:175-184` | failure copy `:172` admits the stored value is unknown |
| Operational gate | `:108` | `!fixtureMode && !privacyMode && connectionStatus === "online" && validId` | actions disabled otherwise |
| Message banner | `:258` | `role="status"`, dismissible | none |

---

## 2. Traced control → state → contract chains (≥5)

**Chain 1 — SSE alert → store → queue row (SC-4 / C-1).**
`backend/api.py:1250` `state.register_alert(payload)` → `:1260` `state.broadcast_alert(payload)` (in-process queues, `:464-471`) → `GET /alerts` SSE `:1589` → `lib/sentinel-store.tsx:76` `new EventSource(SSE_URL)` (`:56`) → `:87` `JSON.parse` → `:94` `parseAlertEnvelope` (`lib/sentinel-selectors.ts:48-102`) → `:95` `dispatch({type:"alert"})` → reducer dedupe + 50-cap + `selectedAlert`/`lastRealAlert` (`:35-41`) → `app/page.tsx:38` `selectVisibleAlerts` → `alert-feed.tsx:91` row.
*Failure:* malformed envelope → `null` → dropped without a UI signal (`sentinel-selectors.ts:59`; store `:96`). `severity: "none"` is a real producer value (`backend/decision_config.py:83-84`, `backend/fusion.py:91`) but the parser whitelist `:54` accepts only `critical|high|medium` → a confirmed alert is silently discarded (R-3, D-4).

**Chain 2 — Cross-filter camera chip → every surface (C-7).**
`alert-feed.tsx:96` `setFilters` → `sentinel-store.tsx:126` `dispatch("filters")` → `selectVisibleAlerts` (`lib/sentinel-selectors.ts:112-122`, band rule `:120`) → consumers: `app/page.tsx:38`, `alert-feed.tsx:40`, `incidents-section.tsx:28` (S-10), `clip-sidebar.tsx:74-89`, `incident-panel.tsx:194/199/204`. *Failure:* invalid `isoTime` is excluded (`:116`), so a malformed alert disappears from every surface at once.

**Chain 3 — Toast: last real alert → single slot → ARIA live region (C-1).**
`sentinel-store.tsx:40` `lastRealAlert` → `app/page.tsx:57-60` (set when `section !== "incidents"`) → `alert-toast.tsx:16` `alert` prop → suppression `:26` → auto-dismiss `:28` → `role="alert" aria-live="assertive"` `:38`. *Failure:* only the newest alert is visible (D-5); review navigates only to that newest alert.

**Chain 4 — Clip listing → modal → replay fetch (C-4d, C-4a-adjacent).**
`clip-sidebar.tsx:93` `apiFetch(API_BASE + "/api/clips/list")` → `backend/api.py:1711-1735` (EVIDENCE_DIR glob, joins alert metadata from `state.get_alert`) → `parseClips` `:38-55` → related filter `:74-89` → card `:143` → modal `:151` → `IncidentReplay` `:155` → `incident-replay.tsx:66` `apiFetch(API_BASE + "/clips/" + id)` with 404 retry `:68-70` → object URL `:74` → `<video>` `:117`. *Failure:* list error → retry state; clip 404 loop ×10 then `error` with retry; disconnected ⇒ no polling at all, `status` stays at its prop-derived value (`:69`).

**Chain 5 — Evidence chain ledger → dossier custody row (C-4a).**
`incident-panel.tsx:124` `apiFetch(API_BASE + "/evidence_chain/" + id)` → `parseEvidenceChainRecord` (`lib/local-report.ts:33`) → panel `:221-223`; refresh `:220` re-runs the effect via `chainRefresh`. *Failure:* 404 is a distinct `unavailable` state ("لم توفر الخدمة قيداً لهذه الحادثة بعد") vs network/parse `error` ("تعذر جلب القيد").

**Chain 6 — Policy mutation sliders → backend (C-6 / F-35).**
`incident-panel.tsx:166-169` `POST /set_threshold` `{threshold: value/100}` → `backend/api.py:2109-2113` `state.set_threshold` (`:529`) → audit log; cooldown `POST /set_cooldown` → `:553`. *Failure:* non-OK → "تعذر حفظ الضبط. القيمة الحالية في الخدمة غير معروفة." (`:172`) — no read-back endpoint exists, and the panel says so `:255`.

**Chain 7 — Person count envelope → overview counter (event ≠ alert vocabulary).**
`sentinel-store.tsx:88` `parsePersonCountEnvelope` (`lib/sentinel-selectors.ts:104-110`) → `:91` `dispatch({type:"person"})` → `personCount` → `app/page.tsx:96-98` → overview. No alert is created from a person event. *Note:* the producer has no committed caller (N-2), so this branch is dormant at baseline.

---

## 3. Incident workflow as-built vs WT-11 patterns (§5 of the WT-11 research)

| WT-11 recommendation | As-built at baseline | Gap |
|---|---|---|
| **T25-1** four-state triage (`جديد → قيد المعالجة → مُعلَّق → مُغلق`), ack flagged, actor recorded | **No triage state at all.** "Selection" only: `sentinel-store.tsx:42` `select`, `selectedAlert`; no per-alert status, no ack, no actor, no timestamp. The only workflow verbs are honest dead ends (`incident-panel.tsx:245-246`). | the whole state machine is missing (D-13) |
| **T25-2** triage verbs (`a`/`c`) + visible shortcut list | `j/k/Enter` exist in `incidents-section.tsx:36-51` (S-10) and roving arrows in `alert-feed.tsx:62-65`; no ack/close verbs, no discoverable shortcut list | partial |
| **T25-9** single severity ordering comparator (`critical > high > medium`, newest-first tie-break) | No shared comparator. Queue order is arrival order (`sentinel-store.tsx:38` prepend); history sorts by `isoTime` only (`alert-history.tsx:43`); 8 duplicate severity maps (D-1) | missing |
| **T25-6** export dialog showing custody facts + a verification badge driven by the real ledger result | Evidence chain panel exists (`incident-panel.tsx:219-224`) and distinguishes `unavailable`/`error`/`ready`, but there is **no "فشل التحقق" (verification-failed) badge** for a broken `prevHash → currentHash` link, and no export-time custody summary | partial |
| **T25-7** case-file continuity (status + activity feed), labelled session-scoped | No status, no activity feed. `selectedAlert` is the only case state; cookies session-only (`G-10`) | missing |
| **T25-5** replay pre/post roll, scrubber marker, gap-skip, speed | Marker exists (`incident-replay.tsx:135`), no pre/post roll, no gap-skip, no speed control (only `clip-player.tsx:22` has speed, and it is not used by the dossier) | partial |
| **T25-4** mute that never hides counts | No mute concept; type filtering exists (`CrossFilters.type`) | missing |
| **T25-3** group/dedupe with counters | none | missing |
| **T25-10** audit surface (`GET /audit/recent`) | not consumed anywhere in my slice | out of slice (U-07) |

**Severity vs confidence discipline (T25-1 / S26-6).** Severity is the coloured triage axis (`alert-feed.tsx:92` label, `incident-panel.tsx:194` chip, `alert-toast.tsx:35`); confidence appears as a bare percentage in three places — feed bar + title `alert-feed.tsx:98`, toast `alert-toast.tsx:42`, replay meta `incident-replay.tsx:164` — without a scale label or the backend's `calibrationStatus: "unverified"` (`backend/fusion.py:117`). Only `incident-panel.tsx:217` states the disclaimer. WT-11 asks for `درجة (غير معايرة)` wording wherever a score is triaged on; that is not yet implemented (D-2).

**Ack semantics.** Vendors separate "whose alert is it" (list filter) from "what do I do with it" (row action), and record the acting user when the state changes (WT-11 research §3 rows 1–2). At baseline there is no ack action, so no actor can be recorded. The backend does keep an in-memory alert registry with an unused update hook (`backend/api.py:595` `register_alert`, `:616` `update_alert` — **no caller**), and a 42-route security posture where mutations must authorize (R-8). Persistence write path therefore needs an additive route (§4 D-13).

---

## 4. Drift / risk register (input to Phase B)

| ID | Risk | Evidence | Phase B intent |
|---|---|---|---|
| D-1 | Severity label maps duplicated 8×: `alert-feed.tsx:20-24`, `alert-history.tsx:11-15`, `alert-toast.tsx:35-36`, `incident-panel.tsx:30`, `incidents-section.tsx:9` (S-10), `category-filter.tsx:17-21`, `ui-intel-ops-section.tsx:21` (S-10), `geo-dashboard.tsx:22` (S-10) | grep `حرج` across `components/` | single source in `lib/sentinel-selectors.ts` (additive, flagged); remove drift in my 4 files; flag the S-10/S-13 copies as recommendations |
| D-2 | Confidence rendered as bare percentage without scale/calibration label | `alert-feed.tsx:98`, `alert-toast.tsx:42`, `incident-replay.tsx:164` | label as uncalibrated score; severity remains the triage axis |
| D-3 | `categories`/`primaryCategory`/`allCategories` declared on `LiveAlert` but **not produced** by the backend | `backend/api.py:898-1000` payload has `weaponLabels`/`threatType` only; `/api/categories` (`:1744`) is a capability list, a different thing; ui-contract §C-1 note | **do not** wire parsers; record verification |
| D-4 | R-3 made concrete: `severity: "none"` is producible (`backend/decision_config.py:83-84`; `backend/fusion.py:91`, `:95`) but `parseAlertEnvelope` rejects it (`lib/sentinel-selectors.ts:54`) → confirmed alerts dropped silently | source trace above | additive tolerant normalization + flagged SC-4 delta note |
| D-5 | Toast is single-slot | `app/page.tsx:34`, `:57-60` | stacked queue (page wiring granted by orchestrator) |
| D-6 | No deep-linking (G-1) | `app/page.tsx:27` `useState("overview")` | `?section=&id=` read on mount (flagged page hunk) |
| D-7 | Replay badge derived from a cameraId prefix heuristic | `alert-feed.tsx:88` | derive from fixture/demo provenance, not a magic prefix |
| D-8 | History clock frozen at mount | `alert-history.tsx:39` | tick the relative clock |
| D-9 | Clip modal has no focus trap / restoration | `clip-sidebar.tsx:151-159` | trap + restore focus |
| D-10 | Malformed SSE envelopes swallowed silently | `sentinel-store.tsx:96` | (out of slice; recorded) |
| D-11 | "Clear filters" sets `range: "all"` | `alert-feed.tsx:80` vs empty-state copy | clear filters without silently widening the window |
| D-12 | Unused generic toast system (`components/ui/toaster.tsx`, `hooks/use-toast.ts`, `components/ui/sonner.tsx`) never mounted | grep `Toaster` in `app/` | hygiene note; do not adopt for alerts (alerts must use the APG alert pattern) |
| D-13 | No triage state/persistence anywhere | `sentinel-store.tsx` state shape `:10-18`; `update_alert` has no caller `backend/api.py:616` | additive triage route + store state machine, honest session-scope labeling when the API is absent |

---

## 5. Gaps I will not close (scope), and where they go

- **G-1 deep-linking** beyond the granted `?section=&id=` read on mount (e.g. real routes) → recommendation.
- **G-3 camera health** is hardcoded honest "unavailable" and no camera-presence endpoint is consumed → recommendation (U-07/U-01).
- **G-9 SSE unauthenticated** (`EventSource` cannot send `X-API-Key`) → recommendation (S-19).
- **G-10 50-alert session cap** drops older alerts silently (`sentinel-store.tsx:38`) → surface the cap in the UI copy; a real history API is out of slice.
- **G-2 reports screen**, **G-7 geolocation**, **G-8 manifest theme-color** → other slices.
- **T25-10 audit surface** (U-07) → other slice.
