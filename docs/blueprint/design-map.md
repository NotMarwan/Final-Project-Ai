---
authority: scoped
non_authoritative: true
---
# AI Sentinel — root frontend design map (verified inventory)

Campaign: AI Sentinel improvement campaign, work ticket WT-02 (Design blueprint).
Worktree: `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-02`, branch `codex/sentinel-02-design-map`, baseline `e86d34b` (`docs: regenerate current state and design system after the rebuild`).
Verification date: 2026-09-29. All claims below were verified against the pinned source by reading files and running `npm run typecheck`, `npm run lint`, and `node scripts/docs-contract.mjs --check` in this worktree. No browser run was performed; browser-dependent items are explicitly marked **[UNVERIFIED — browser]**.

This document is the inventory UI agents implement against. It records what the code does today, not what any presentation or older document claims.

## 0. Design authority (and non-authority duplicates)

**Authority (in this order):**

1. `app/globals.css` — semantic token system (`:root` dark default + `.light` theme), `@theme inline` mapping, utilities, motion, responsive overrides. Loaded by `app/layout.tsx:7` (`import './globals.css'`).
2. `app/layout.tsx` — font loading, `lang="ar" dir="rtl"`, ThemeProvider, service-worker registration.
3. `components/ui/` — shadcn-style primitives ("new-york" preset per `components.json`), see §2.1 for the implemented subset.
4. `app/page.tsx` + `components/` + `lib/` + `hooks/` — the implemented single-page dashboard.

**Non-authority duplicates (recorded, do NOT extend):**

| Path | What it is | Evidence |
|---|---|---|
| `styles/globals.css` | Import-only alias: single line `@import '../app/globals.css';` | file content (1 line) |
| `frontend/` | Historical duplicate tree reduced to `frontend/README.md`, which itself states it has "no independent release, design-system or runtime-readiness authority" | `frontend/README.md` |
| `components/احتياطي/` ("backup") | 3 legacy component copies (`dashboard-header.tsx`, `incident-panel.tsx`, `video-player.tsx`) that use raw `fetch` and literal hex colors (`#334155`, `#64748b`, `#ef4444`, `#0f172a` at `components/احتياطي/incident-panel.tsx:248–284`) instead of `apiFetch` + semantic tokens | grep for hex colors + `fetch(` |
| `components/files.zip`, `components/files (1).zip` | Stray archives committed inside the source tree (repo-hygiene debt, U-09 gap) | directory listing |
| `lib/dashboard-data.ts` | Legacy demo dataset (`Alert` type with `Fighting/Panic/Vandalism/Intrusion`, English `timeAgo` strings, floor-plan data) — 0 importers | import grep (see §2.3) |
| `lib/model-compatibility.ts` | `normalizeToMultiThreat` model-output adapter — 0 importers | import grep (see §2.3) |

`docs/CURRENT.md` (generated) independently states the same authority rule: "Root frontend source is authoritative; frontend/, design_extract/ and presentations are not alternate runtime authorities."

## 1. Screens/routes inventory (stable feature IDs)

**Routing fact:** the app is a single Next.js route. `app/page.tsx` is the only page; "screens" are in-page sections switched by React state (`section`), not URLs. There is no per-screen URL, no router, and no deep-linking except the dev-only fixture flag. IDs `U-01`…`U-10` are the campaign-stable identifiers.

> **ID renumbering (blueprint seed):** this map originally published its screen IDs as `F-01`…`F-10`. The campaign seed renumbers them to `U-01`…`U-10` so that `F-01`…`F-49` stay reserved for the runtime feature inventory (`docs/blueprint/runtime-map.md` §2). No other content changed. Cross-references live in `docs/blueprint/index.json`.

Route/entry points:

- `/` → `app/page.tsx` → `DashboardPage` wraps `Dashboard` in `SentinelProvider` (`app/page.tsx:111`).
- `/?fixtures=1` → dev-only UI fixture mode (`lib/ui-fixtures.ts:6` `fixturesEnabled`, gated by `NODE_ENV !== "production"`; loads 18 synthetic alerts via `makeUiFixtures`, `lib/ui-fixtures.ts:12`).
- `app/manifest.ts` → PWA manifest (`/manifest.webmanifest`); `public/sw.js` service worker registered in `app/layout.tsx:65` in production only (dev unregisters SWs).
- Section navigation entry points: rail buttons (`components/shell/app-shell.tsx:38`), number keys `1–7` (`app/page.tsx:46–53`), command palette `Ctrl/Cmd+K` (`app/page.tsx:44`, `components/shell/command-palette.tsx`), `Overview` "فتح المراقبة الحية" button (`components/overview/overview.tsx` `onOpenMonitor`), toast click (`app/page.tsx` `AlertToast onNavigate`), AccessNotice "إدخال المفتاح من قسم النظام" (`components/shell/access-notice.tsx:15`).

Section registry `SECTIONS` (`components/shell/app-shell.tsx:10–18`): `overview`, `monitor`, `demo-clips`, `incidents`, `intelligence`, `operations`, `system` — all labels Arabic; keyboard index rendered as `.rail-shortcut`.

### U-01 Overview — `section === "overview"` (`app/page.tsx:94`)

- Component tree (top 2 levels): `Overview` (`components/overview/overview.tsx`) → { `HeroIncidentInstrument`, `OverviewCharts` (dynamic, chart skeleton loading state), `StatCard` ×6, `Sparkline`, `AnimatedValue`, active-filter chips, latest-incidents list, offline panel }.
- Data/hooks: `useNow(15_000)` (`hooks/use-now.ts`), `useSentinel()` store values `alerts, filters, connectionStatus, fixtureMode`; selectors `selectVisibleAlerts`, `countsBySeverity`, `countsByType`, `latencyPercentiles`, `previousWindowCount`, `timeBuckets` (`lib/sentinel-selectors.ts`); timeline helpers `makeTimeline`, `inTimeWindow`, `windowForBuckets` (`components/overview/overview-time.ts`).
- Backend endpoints: none directly (session alert data only, via the store SSE stream — see §4).
- Stats shown: alerts in window, critical, weapon, violence, alert latency `p50/p95` (`latencyPercentiles`, needs ≥2 samples), active cameras = hardcoded "غير متاح" (honest empty, `overview.tsx` StatCard `label="الاميرات النشطة"` → `value="غير متاح"`).
- Cross-filter dimension isolation: camera chart re-queries without `cameraId`, severity chart without `severity`, confidence chart without `confidenceBand`, timeline without `cameraId`/`type`, context panel only `range` (`overview.tsx` `chartDimensions`).

### U-02 Live Monitor — `section === "monitor"` (`app/page.tsx:96`)

- Component tree: `UiMonitorSection mode="monitor"` (`components/sections/ui-monitor-section.tsx`) → { `SectionHeader`, source buttons (`LIVE_SOURCES` = `CAM-01`, `CAM-02`), `StatusBadge`, `OverlaySettingsPanel`, `VideoPlayer` (dynamic), feed slot = `AlertFeed`, `AlertHistory` }.
- Data/hooks: `useSentinel()`; `selectVisibleAlerts` for `AlertHistory`; `VideoPlayer` internally uses `useDetectionStream(cameraId)` (`components/video-player.tsx:117`).
- Backend endpoints (inside `VideoPlayer`): `GET/POST /api/webrtc/{cameraId}` (`video-player.tsx:148`), MJPEG fallback `GET /video_feed?camera_id=…&k={streamKey}` (`video-player.tsx:164`), SSE `GET /detections?camera_id=…` (§4 chain A). `POST /demo_start/{id}`, `DELETE /demo_stop/{id}` only from demo selection (`app/page.tsx:68,75`).
- Source-state badge mirrors `VideoPlayer.onSourceStateChange` into `UiMonitorSection` `sourceState`; `displayState` is forced to `offline` when `fixtureMode || connectionStatus !== "online"` (`ui-monitor-section.tsx` `displayState`).

### U-03 Demo Clips — `section === "demo-clips"` (`app/page.tsx:98`)

- Same `UiMonitorSection` with `mode="demo"`; sources `EXAMPLE-01..03` (`DEMO_SOURCES`, labels عينة اعتداء/عنف). Selecting a sample calls `chooseDemo` → `POST /demo_start/{id}` (`app/page.tsx:75`); leaving the section stops it with an immediate + 500 ms retry `DELETE /demo_stop/{id}` via `buildDemoStopPlan` (`lib/live-visual-state.ts:243`, used at `app/page.tsx:78`).
- `VideoPlayer` treats `EXAMPLE-*` as `isDemo`; demo frames come from the same `/video_feed` endpoint (`demoSrc`, `video-player.tsx:166`) with a 4 s `DEMO_LOADING_MS` grace (`video-player.tsx:81`).
- Header copy states results here are replay, not live observation (`ui-monitor-section.tsx` `SectionHeader`).

### U-04 Incidents & Evidence — `section === "incidents"` (`app/page.tsx:100`)

- Component tree: `IncidentsSection` (`components/sections/incidents-section.tsx`) → { queue aside (`AlertFeed` slot `feed`), dossier (`IncidentPanel`, dynamic), related clips (`ClipSidebar`, dynamic), filter chips, keyboard cursor }.
- Data/hooks: `useSentinel()`; `selectVisibleAlerts`; `incidentEvidenceFacts`, `parseEvidenceChainRecord` (`lib/local-report.ts`); `IncidentReplay` (`components/incident-replay.tsx`) with `getContainedVideoRect`/`projectOverlayBox` (`lib/live-visual-state.ts`) for detection-box overlay at the detection moment (±0.7 s).
- Backend endpoints: `GET /evidence_chain/{alertId}` (`incident-panel.tsx:102`), `GET /download_evidence/{alertId}` with HTTP 202 polling up to 20 × 1.5 s (`incident-panel.tsx:132`, constants `MAX_POLL_ATTEMPTS`/`POLL_INTERVAL_MS`), `GET /download_report/{alertId}` (`incident-panel.tsx:152`), `POST /set_threshold` `{threshold: value/100}` and `POST /set_cooldown` `{cooldown: value}` debounced 400 ms (`incident-panel.tsx:166`), `GET /clips/{alertId}` (`incident-replay.tsx:66`), `GET /api/clips/list` (`clip-sidebar.tsx:93`).
- Keyboard: `j`/`k` move queue cursor, `Enter` opens (`incidents-section.tsx:43` handler); critical alerts announced through `aria-live="assertive"` region (`incidents-section.tsx:72`).

### U-05 Intelligence — `section === "intelligence"` (`app/page.tsx:102`)

- Component tree: `UiIntelOpsSection section="intelligence"` (`components/sections/ui-intel-ops-section.tsx:62`) → { `Heading` (index 05), `FilterStrip`, `IncidentList`, alert-facts panel, `FixtureSummary` (fixture mode only), `AiReport` (dynamic, local + DeepSeek summaries), `Empty` fallback }.
- Data/hooks: `useSentinel()`; `selectVisibleAlerts`; type/severity filter toggles write back into `CrossFilters`.
- Backend endpoints (in `AiReport`, `components/ai-report.tsx`): `GET /reports/local/{alertId}` (`:76`, 404 → `missing`, 401/403 → reader-required error state), `GET /reports/deepseek/status` (`:106`, `apiKeyPresent`), `GET /reports/deepseek/{alertId}` (`:112`), `POST /reports/deepseek/{alertId}?force={bool}` (`:127`).

### U-06 Operations — `section === "operations"` (`app/page.tsx:104`)

- Component tree: `Operations` (`ui-intel-ops-section.tsx:68`) → { `Heading` (index 06), severity filter buttons, `GeoDashboard` (dynamic, illustrative floor plan from `lib/dashboard-data.ts`-style room geometry — see gap G-7), `TelegramStatusCard` (dynamic) }.
- Backend endpoints (in `TelegramStatusCard`, `components/telegram-status.tsx`): `GET /system/status` (`:41`, reads `notifications` object; 30 s polling), `POST /notifications/telegram/test` (`:69`).
- Alert count is suppressed to "—" when `connectionStatus !== "online" && !fixtureMode && visible.length === 0` (`ui-intel-ops-section.tsx` `unavailable`).

### U-07 System — `section === "system"` (`app/page.tsx:106`)

- Component tree: `System` (`ui-intel-ops-section.tsx:76–86`) → { `Heading` (index 07) + "إعادة التحقق" reload button, 4 `StatusCard`s (alert channel / server response / inference device / camera health), session-alerts counter grid, `ApiAccess` (dynamic), `TelegramStatusCard` }.
- Data/hooks: `useApiAccess()` (`hooks/use-api-access.ts`); local `health` state polled every 30 s via `GET /health` (`ui-intel-ops-section.tsx:76`), mapping `health.health === "ok"` and `health.model.device`.
- Backend endpoints: `GET /health`, `GET /security/status` (`hooks/use-api-access.ts:22`), `GET /security/session` (`hooks/use-api-access.ts:29`, `components/api-access.tsx:23`).
- Honest gaps surfaced in UI: camera health card is hardcoded `value="غير متاح"` with source text "لا توجد قراءة صحة للمصدر هنا" (`ui-intel-ops-section.tsx:85`).

### U-08 App shell & global chrome (cross-cutting)

- `AppShell` (`components/shell/app-shell.tsx`) — command rail (brand lockup, 7 `rail-item` buttons with `aria-current="page"`, collapse toggle), `DashboardHeader` (`components/dashboard-header.tsx` — UTC clock, theme toggle via `next-themes`, privacy toggle `aria-pressed`, palette trigger with `⌘ / Ctrl K` hint), `AccessNotice` (`components/shell/access-notice.tsx`, `role="status"`, shown when `useApiAccess().state === "required"`), fixture banner (`role="status"`), `CommandPalette` (`components/shell/command-palette.tsx`, `role="dialog" aria-modal="true"`, Escape closes, filters sections + alerts, quick privacy action), `AlertToast` (`components/alert-toast.tsx`, `role="alert"`/`status`, `aria-live` assertive/polite, suppressed on the incidents tab via `isToastSuppressedForTab` (`lib/live-visual-state.ts:241`)).
- Hydration marker: `document.documentElement.dataset.hydrated = "true"` after mount (`app-shell.tsx:33`) for browser tests.
- Keyboard model: `1–7` section shortcuts + `Ctrl/Cmd+K` palette (`app/page.tsx:44–53`); shortcuts ignored while typing in inputs/contenteditable.

### U-09 Design system: tokens, typography, RTL, a11y, responsive (cross-cutting) — §3

### U-10 Shared UI data contracts — `docs/blueprint/ui-contract.md` (this ticket)

## 2. Component/state inventory

### 2.1 Primitives (`components/ui/`) — implemented vs unused

55 primitive modules exist (shadcn "new-york" set). Only **5 are imported by app code** outside `components/ui/`:

| Primitive | Consumers |
|---|---|
| `ui/popover`, `ui/slider` | `components/overlay-settings.tsx` (overlay settings popover: 6 toggles, opacity slider, box-thickness slider, label-style) |
| `ui/slider` | `components/clip-player.tsx` (dead, see §2.3) |
| `ui/badge`, `ui/button`, `ui/switch` | `components/احتياطي/*` backup copies only |

The remaining 50 (`accordion`, `alert`, `alert-dialog`, `avatar`, `calendar`, `carousel`, `chart`, `checkbox`, `command`, `dialog`, `drawer`, `dropdown-menu`, `form`, `input`, `select`, `sheet`, `sidebar`, `sonner`, `table`, `tabs`, `toast`, `toaster`, `tooltip`, …) are **not imported by any app component** — verified by per-module import grep. `components/ui/sidebar.tsx` and `components/ui/toaster.tsx` pull `@/hooks/use-mobile` and `@/hooks/use-toast`, which exist twice (`hooks/use-mobile.ts` vs `components/ui/use-mobile.tsx`; `hooks/use-toast.ts` vs `components/ui/use-toast.ts`) — duplicated modules, only the `hooks/` copies are referenced.

Consequence for UI work: the design authority for new UI is `app/globals.css` tokens + the bespoke shell/section components (`components/shell/*`, `InstrumentPanel`, `InstrumentValue`), not the unimplemented shadcn variants. The custom toast system (`AlertToast`) is the live notification mechanism; `ui/toast`+`ui/toaster`+`ui/sonner` are unused.

### 2.2 Meaningful UI states actually handled (with evidence)

Shared visual-state vocabulary `SourceVisualState = "live" | "replay" | "stale" | "offline" | "loading" | "unverified"` (`lib/live-visual-state.ts:3`), decided by `sourceVisualState()` (`lib/live-visual-state.ts:27–43`); Arabic labels + token colors in `ui-monitor-section.tsx` `STATE_LABEL`/`STATE_COLOR` and `video-player.tsx` `STATE_COPY`/`STATE_TOKEN`.

| Screen | Loading | Error | Empty | Stale | Replay | Live | Offline/disconnected | Fixture/preview |
|---|---|---|---|---|---|---|---|---|
| U-01 Overview | chart skeletons while `OverviewCharts` loads (`overview.tsx` dynamic `loading`) | — | `offline-panel` with different copy for offline vs filtered-empty (`overview.tsx` `!hasContextData`) | not shown per-source (no source) | — | — | hero `hero-offline`, "؟" gauge, counts "—" (`overview.tsx`) | `fixtureMode` copy + `/?fixtures=1` dev link |
| U-02/U-03 Monitor/Demo | `loading` state + demo 4 s grace (`video-player.tsx:81`), `جارٍ التحقق من المقطع` in replay | `streamError` → offline panel; WebRTC `onError` → MJPEG fallback; `setError("Invalid detection data")` (`use-detection-stream.ts:82`) | feed empty states (below) | `stale` badge + `قراءات التحليل قديمة` (`video-player.tsx` `statusLine`) | `replay` badge (`StatusBadge`, demo copy) | `live` badge (requires frame + live source + fresh analysis — footer copy in `ui-monitor-section.tsx`) | `offline` badge + empty video plate | fixture banner forces `displayState="offline"` |
| U-04 Incidents | evidence polling `loading` (`incident-replay.tsx` status, `incident-panel.tsx` chain `loading`), 404 → auto-retry ×10 every 2 s | chain `error`, download/report `error` messages (`incident-panel.tsx` `Message`) | "اختر تنبيهاً لفتح ملف الحادثة" (`incident-panel.tsx`); clips empty ("لا يوجد مقطع دليل", `incident-replay.tsx`); selected-alert-outside-filter note (`incidents-section.tsx` end) | connection banner "قد تكون بيانات هذه الحادثة قديمة" (`incident-panel.tsx`) | "دليل مسجل · ليس بثاً حياً" badge (`incident-replay.tsx`) | — | channel badge "قناة التنبيهات غير متصلة" (`incidents-section.tsx`) | fixture dossier banner |
| U-05 Intelligence | local report `loading` | `error` states w/ 401/403 reader message (`ai-report.tsx:79,85`) | `missing` (404) and `Empty` panel | — | `FixtureSummary` labeled عينة واجهة | — | offline wording in report panel | fixture summary replaces evidence claims |
| U-06 Operations | telegram `loading` (`telegram-status.tsx`) | `unavailable` on fetch failure | `unavailable` GeoDashboard state | — | — | — | counts "—" (`ui-intel-ops-section.tsx` `unavailable`) | fixture flag |
| U-07 System | `healthState: "loading"` (`ui-intel-ops-section.tsx:76`) | `offline` on health failure; access `offline` (`api-access.tsx`) | access `unconfigured` state | checked-at timestamp shown | — | stream "متصلة" | 4 status cards report honestly (camera health "غير متاح") | fixture banner |
| Global | `useApiAccess` `checking` | expired key message (`api-access.tsx`) | feed empty ×3 variants (`alert-feed.tsx`: filtered / offline / no alerts) | alert age via `formatAlertRelativeArabic` from one feed clock (`alert-feed.tsx` `useFeedClock`, 60 s) | toast carries `LiveAlert` | toast suppressed on incidents tab | reconnecting grace 2 s then offline, auto-reconnect 3 s (`sentinel-store.tsx:96–110`) | `fixture-banner` |

AlertFeed empty-state split evidence: `alert-feed.tsx` — `emptyIsFiltered` ("لا تنبيهات تطابق التصفية" + clear-filters button) vs `connectionStatus === "offline" && !fixtureMode` ("قناة التنبيهات غير متصلة") vs default ("لم ترد تنبيهات ضمن الفترة").

### 2.3 Disconnected controls, duplicates, dead code

| Finding | Evidence | Classification |
|---|---|---|
| `ClipSidebar.onDeleteClip?: (alertId: string) => void` declared but never passed by any caller and never invoked inside the component | prop at `components/clip-sidebar.tsx:31`; no other reference in repo | disconnected/dead prop — delete-clips affordance is not wired |
| `lib/dashboard-data.ts` — legacy `Alert` schema (`Fighting/Panic/Vandalism/Intrusion`, English copy, floor-plan rooms) | 0 importers (import grep) | dead code |
| `lib/model-compatibility.ts` — `normalizeToMultiThreat`, `ModelOutput` | 0 importers (import grep) | dead code |
| `components/clip-player.tsx` + `hooks/use-clip-playback.ts` | `clip-player` 0 importers; `use-clip-playback` imported only by `clip-player` | dead code (transitive pair) |
| Unused exports in `lib/detection-types.ts`: `CATEGORY_ICONS`, `CATEGORY_COLORS`, `CategoryCapability`, `CategoryConfig` | symbol grep finds no use outside `detection-types.ts` | dead exports (types kept in ui-contract as wire-format candidates only where parsed) |
| `components/احتياطي/*` legacy copies (raw `fetch`, hex colors) | §0 table | non-authority duplicates |
| `components/ui/use-toast.ts` vs `hooks/use-toast.ts`; `components/ui/use-mobile.tsx` vs `hooks/use-mobile.ts` | both copies exist; only `hooks/` copies referenced | duplicated modules |
| 50 of 55 `components/ui/*` primitives unimported (incl. entire toast subsystem) | §2.1 | dead weight (keep as authority reference or prune — orchestrator decision) |
| `components/files.zip`, `components/files (1).zip` inside `components/` | directory listing | repo-hygiene debris |
| `alert-feed.tsx` and `category-filter.tsx` begin with a UTF-8 BOM (`\ufeff`) | file head bytes | cosmetic debt |
| `IncidentReplay.onClose` optional; only rendered when supplied | `incident-replay.tsx` props | fine (used by sidebar modal path) |
| Duplicate `SEVERITY_LABEL` maps in ≥5 components | `alert-feed.tsx`, `incidents-section.tsx`, `ui-intel-ops-section.tsx`, `overview.tsx`, `incident-panel.tsx` | duplication risk (labels drift) |

### 2.4 Components using literal colors instead of semantic tokens

Active app code is clean: the only literal hex values outside `components/ui/` are `app/layout.tsx:47` (`viewport.themeColor: '#090c0e'` — matches `--surface-0`) and `app/manifest.ts:11–12` (`#0f172a` theme/background — does **not** match `--surface-0: #090c0e`, see gap G-8). Inside `components/ui/chart.tsx:58` shadcn's tooltip uses `#ccc`/`#fff` fallbacks. Literal colors otherwise appear only in the non-authority `components/احتياطي/incident-panel.tsx` (§0). Canvas drawing colors are code-side RGB arrays in `lib/detection-envelope.ts`/`lib/model-compatibility.ts` (`color: [r,g,b]` wire format), not CSS.

## 3. Token / typography / RTL / a11y / responsive verification

### 3.1 Tokens

- Source: `app/globals.css:5–81` (`:root` "Tactical Command foundation") + `.light` theme (`:82–104`) + `@theme inline` shadcn mapping (`:106+`).
- Core semantic tokens: `--surface-0..3`, `--border-hairline`, `--text-primary/secondary/tertiary`, `--signal`, `--signal-contrast`, `--threat-critical/high/medium`, `--cat-weapon`, `--cat-violence`, `--state-live/replay/stale/offline`, `--radius`, `--radius-panel`, `--shadow-panel`, `--glow-live`, `--glow-critical`, `--motion-fast/base/slow`, `--ease-instrument`; plus shadcn aliases (`--background`, `--primary`, `--chart-1..5`, `--sidebar-*`, `--danger`, `--success`, `--warning`, `--hud-cyan`, `--monitor-idle/alert/warning`).
- `docs/DESIGN.md` (generated by `npm run docs:sync`) lists **the same token names and values** — spot-checked table (`--surface-0 #090c0e` … `--ease-instrument cubic-bezier(.2,.8,.2,1)`) matches `app/globals.css` exactly; stylesheet fingerprint `b5a9c4d6…44d2` recorded in `docs/DESIGN.md:5`. `docs/design-tokens.json` is the generated machine copy. No drift found between stylesheet and generated design doc. `docs/DESIGN.md` also names the same authoritative sources as §0.

### 3.2 Typography & font loading

- `app/layout.tsx:10–15`: `IBM_Plex_Sans_Arabic` via `next/font/google`, subsets `arabic`+`latin`, weights 400/500/600/700, `display: 'swap'`, CSS variable `--font-arabic`. `GeistMono` via `geist/font/mono` as `--font-geist-mono`.
- `@theme inline` maps `--font-sans: var(--font-arabic), sans-serif` and `--font-mono: var(--font-geist-mono), 'Geist Mono', monospace` (`app/globals.css:107–108`); body uses `font-sans` (`app/layout.tsx:58`).
- Numerals: `components/shell/locale.ts` normalizes Arabic-Indic digits to Latin (`normalizeLatinDigits`) and formats with `ar-SA-u-ca-gregory-nu-latn` (Gregorian + Latin digits, `formatTime24`/`formatDateTime24`); technical values render through `InstrumentValue` (`components/shell/primitives.tsx`) in a `<bdi dir="ltr">` with `instrument-num` (tabular) styling, Arabic fallback text switches to `font-sans` + `dir="auto"`.

### 3.3 Arabic/RTL — actually implemented

- `<html lang="ar" dir="rtl">` (`app/layout.tsx:57`); `UiIntelOpsSection` root adds `dir="rtl"` (`ui-intel-ops-section.tsx:88`).
- Logical properties used throughout: `start-*/end-*`, `inset-inline-start` (`incident-replay.tsx` box overlay + detection marker), `ms-*/me-*`, `border-s-2` (`ui-intel-ops-section.tsx` FixtureSummary). LTR islands are explicitly `dir="ltr"` (timeline plot, ribbon lanes, seek slider, IDs, kbd hints).
- Bidirectional isolation via `<bdi>` for IDs/timestamps (`primitives.tsx`, `command-palette.tsx`, many panels).
- Verdict: RTL is genuinely implemented, not a label swap. Rendering fidelity (fonts, bidi ordering of mixed strings, logical-property behavior in the canvas overlay projection) is **[UNVERIFIED — browser]**.

### 3.4 Keyboard access / focus (source evidence)

- Visible focus rings: `focus-visible:outline-2 focus-visible:outline-[var(--signal)]` applied on interactive elements across `alert-feed`, `incident-panel`, `incident-replay`, `category-filter`, `overview-charts`, `clip-player`, etc. (grep-verified pattern).
- Keyboard flows: `1–7` sections + `Ctrl/Cmd+K` palette (`app/page.tsx:44–53`); incidents `j`/`k`/`Enter` cursor (`incidents-section.tsx:43–56`, cursor badge shows focused alert id); `AlertFeed` rows implement `ArrowUp/ArrowDown/Home/End` roving focus (`alert-feed.tsx` `handleRowKey` + `data-alert-index`); palette closes on `Escape` (`command-palette.tsx:17`).
- ARIA: `aria-current="page"` on rail; `aria-pressed` on toggles (privacy, severity, chart filters, source buttons); `role="dialog" aria-modal="true"` palette; `aria-live` polite/assertive regions (`alert-toast.tsx:38`, `incidents-section.tsx:72`, feed list `aria-live="polite"`); `role="status"` on fixture banner/access notice/report panels; `aria-label`s on icon-only buttons; `sr-only` critical announcement (`incidents-section.tsx:72`).
- `prefers-reduced-motion` handled in `app/globals.css:484,793,902` and `motion-reduce:` utilities (e.g. `incident-replay.tsx` spinner).
- The e2e suite (`tests/e2e/test_operator_flows.py`) covers rail/keyboard navigation of all 7 sections, Ctrl+K palette, j/k cursor, privacy mode, theme persistence, mobile bottom navigation without horizontal scroll, and per-section console-error checks — but those runs were not re-executed in this ticket.

### 3.5 Responsive breakpoints actually used

- Tailwind responsive prefixes in TSX (counted): `sm:` 48, `md:` 27, `lg:` 12, `xl:` 11. Default Tailwind breakpoints (640/768/1024/1280 px).
- Custom media queries in `app/globals.css`: `max-width: 1260px`, `820px`, `600px` (`:723,730,740`) and `1120px`, `600px` (`:887,892`) for the command shell/overview; hover-gated micro-motion at `@media (hover: hover)` (`:584,628`).
- JS breakpoint: `useIsMobile` at 768 px (`hooks/use-mobile.ts:3`) — consumed only by the unused `ui/sidebar.tsx`.
- Note: two breakpoint systems coexist (Tailwind scale vs custom 1260/1120/820/600). Any responsive change must check both. Actual rendering across widths is **[UNVERIFIED — browser]** (e2e includes a mobile pass, not re-run here).

## 4. Data flow to UI (model observations → components)

All backend communication goes through `apiFetch` (`lib/api-auth.ts:31`) which injects `X-API-Key` from `sessionStorage` (`ai-sentinel-api-key`) for same-origin API calls and forbids redirects; or raw `EventSource` for the two SSE streams (EventSource cannot send headers — the `/alerts` and `/detections` streams are unauthenticated at the transport level, see gap G-9). Base URL: `NEXT_PUBLIC_API_BASE_URL` default `http://localhost:8002`.

### Chain A — detection telemetry & overlay (per camera)

`VideoPlayer` (`components/video-player.tsx:117`) → `useDetectionStream(cameraId)` (`hooks/use-detection-stream.ts:46`) → `EventSource ${API_BASE}/detections?camera_id=…` → for each message:
1. `parseTelemetry(raw, cameraId)` (`lib/pipeline-telemetry.ts:56`) → `PipelineTelemetry` (exact fields in `docs/blueprint/ui-contract.md`), tolerant of snake_case/camelCase wire keys (`inferenceSequence|inference_sequence`, `decision.alertState|alert_state`, `window.framesCollected`, `health|pipeline_health`, …).
2. `parseDetectionOverlayEnvelope(raw)` (`lib/detection-envelope.ts:137`) → `DetectionOverlayEnvelope` (tracks, personCount, isThreat, threatConfidence, fps, weaponScore, videoWidth/Height, multiThreat) — **fail-closed** on malformed data (throws → `setError("Invalid detection data")`, data dropped).
3. Freshness bookkeeping: `updateModalityFreshness` (`pipeline-telemetry.ts:160`) records per-modality completed-observation sequence (`violenceSequence`/`weaponSequence`); history via `appendTelemetryPoint` (`:122`, restart detection, 60 s / 120-point cap, only fresh modality completions get a score point).
4. React receives only sampled updates: `shouldPublishDetectionSnapshot` (`live-visual-state.ts:7`) publishes at most every 1 s or on decision-state change; the canvas reads `overlayRef` per animation frame (`canvas-overlay.tsx`).
5. Consumers: `CanvasOverlay` (boxes/labels/FPS/person count via `getContainedVideoRect`/`getCoveredVideoRect`/`projectOverlayBox`, `live-visual-state.ts:120–215`), `MultiThreatBanner` (`hasViolence/hasWeapon/severity/weaponType`), `ConfidenceBars` (violence/weapon/fused scores), `PipelineTelemetryPanel` (decision state, thresholds, `confirmN/confirmM`, rolling window, cooldown, calibration, health grid, score traces), status line (`decisionState` copy).

Score display rule (`video-player.tsx:127–129`): `telemetry.violenceScore/weaponScore` (0–1) ×100 takes precedence; falls back to `multiThreat.*Score` via `normalizeScoreToPercent` (`live-visual-state.ts:113`, accepts 0–1 or 0–100).

### Chain B — alert stream (session-wide)

`SentinelProvider` (`lib/sentinel-store.tsx:76`) → `EventSource SSE_URL` (`NEXT_PUBLIC_SSE_URL` default `${API_BASE}/alerts`) →
1. `type: "person_detection"` envelopes → `parsePersonCountEnvelope` (`sentinel-selectors.ts:104`) → `personCount` state (feeds `VideoPlayer` person count when telemetry absent).
2. Everything else → `parseAlertEnvelope` (`sentinel-selectors.ts:47`) → `LiveAlert` (required: `id`, `cameraId`, `type ∈ {Violence, Weapon, "Weapon Detection"→Weapon}`, `severity ∈ {critical, high, medium}`, `confidence` 0–100, `timestamp`, ISO `isoTime`, `location`; optional enrichment listed in ui-contract). Malformed envelopes are silently dropped (`catch` in `sentinel-store.tsx:88`).
3. Reducer caps the session list at 50 (`sentinel-store.tsx:36`), dedupes by id, sets `selectedAlert` + `lastRealAlert`. Connection state machine: `onopen` → `online`; `onerror` → `reconnecting`, 2 s grace → `offline`, 3 s reconnect timer (`sentinel-store.tsx:96–110`).
4. Consumers filter through `selectVisibleAlerts(alerts, CrossFilters, now)` (`sentinel-selectors.ts:113`) — range window (`15m|1h|24h|all`), cameraId, type, severity, confidence band (20-point buckets). Derived stats: `countsByType/Severity/Camera`, `timeBuckets`, `confidenceHistogram`, `latencyPercentiles` (p50/p95, ≥2 samples), `previousWindowCount` (delta vs previous equal window), `selectThreatLevel` (15 m critical→high→calm).

### Chain C — staleness & replay computation (exact functions)

| Concern | Function | Rule |
|---|---|---|
| Telemetry stale | `telemetryIsStale` (`lib/pipeline-telemetry.ts:142`) | no snapshot/receipt, or >5 s since receipt, or >5 s since `updatedAt` |
| Inference stale | `inferenceIsStale` (`:147`) | `sequence` null/≤0, or no sample receipt, or >5 s since last completed observation |
| Per-modality staleness | `updateModalityFreshness` (`:160`) + `applyModalityFreshness` (`:187`) | a modality with no new completed observation in 5 s has its score nulled and its health downgraded to `{status:"DEGRADED", reason:"No new <modality> completion received in the last 5 seconds"}` |
| Source visual state | `sourceVisualState` (`lib/live-visual-state.ts:27`) | `failed→offline`; no frame → `loading`(if connected/demo/external) else `offline`; external/demo-without-stream → `replay`; live source without `sourceKind` → `unverified`; stale → `stale`; disconnected → `stale`/`unverified` by `sourceKind`; file source/demo → `replay`; `sourceKind==="live"` → `live` |
| Overlay gating | `useDetectionStream` return (`use-detection-stream.ts:109`) | `data` is null unless `connected && !stale && !inferenceStale` — overlay literally disappears when stale |
| Trace integrity | `appendTelemetryPoint` (`pipeline-telemetry.ts:122`) | sequence regressions reset history (restart); duplicate render frames (same sequence) are not recorded |
| Toast suppression | `isToastSuppressedForTab` (`live-visual-state.ts:241`) | no toast while on the incidents tab |
| Demo teardown | `buildDemoStopPlan` (`live-visual-state.ts:243`) | immediate + delayed retry stop when leaving demo section |

"Replay" is never inferred from timestamps alone: it is `sourceKind === "file"`, `isDemo`, or `externalPlayback` (`NEXT_PUBLIC_LIVE_DEMO_URL` iframe path, `video-player.tsx:174`).

## 5. Gaps (screens/states/risks visible from source)

- **G-1 No URL routes per screen.** Sections are state-only; deep-linking/bookmarking to incidents/evidence/system is impossible except `/?fixtures=1`. Any "screens" workstream must decide whether to introduce routes or keep the single-page shell. (Docs and e2e call them "sections/routes" loosely.)
- **G-2 No dedicated Reports screen.** Reporting exists only as `AiReport` inside U-05 (local summary + DeepSeek) and as `download_report` in U-04. If the campaign expects a reports/evidence screen, it does not exist as a section.
- **G-3 Camera health is absent by design-in-code.** U-07 camera-health card and U-01 active-cameras stat are hardcoded "غير متاح" with honest sourcing; no camera-presence endpoint is consumed anywhere in the frontend. Docs (`docs/CURRENT.md`) acknowledge camera unavailability.
- **G-4 Docs-promised states vs code.** `docs/CURRENT.md` promises "distinguishes replay/offline/stale observations and offers a local Arabic factual summary" — both implemented (§2.2, §4). No additional promised UI states were found unimplemented in `docs/PLAN.md` at this commit; `docs/PLAN.md` holds pending rebuild work per `docs/CURRENT.md` "Work authority". Note `node scripts/docs-contract.mjs --check` currently fails with `Stale generated document: docs/SOURCE-MANIFEST.json` + `Stale generated document: docs/CURRENT.md` (§6) — generated docs are out of date relative to source at baseline.
- **G-5 Contrast/a11y risks from source (no browser audit run):**
  - Heavy use of `text-[10px]` for tertiary text (`--text-tertiary #91a09c` on `--surface-0/1`) — small-type legibility risk; token contrast itself looks adequate on dark, but WCAG AA for 10 px text is **[UNVERIFIED — browser]**.
  - `--threat-medium #93aaa6` doubles as severity text color and `--state-stale`; semantic collision can make "medium severity" read as "stale".
  - Light theme (`.light`) is reachable via the header toggle but every surface was designed dark-first; light-mode contrast is **[UNVERIFIED — browser]**.
  - `AlertToast` is `position: fixed` top-start; with `aria-live` it can announce over content; multi-toast stacking is not implemented (single `toastAlert` slot in `app/page.tsx`).
  - Interactive charts rely on hover for cross-highlight (`hoveredCamera`/`hoveredBucket`); keyboard equivalents exist for bucket selection (`overview-charts.tsx` `onKeyDown` Enter/Space) but not for camera-row hover dimming.
- **G-6 Chart/statistics surface for the statistics workstream** (filter logic exact):
  - `components/overview/overview-charts.tsx` — 4 panels: (01) incident timeline, drag-to-brush time window (`onPointerDown/Move/Up` + `windowForBuckets`, `overview-time.ts:36`), legend toggles `filters.type`; (02) per-camera bars toggle `filters.cameraId` (hover cross-highlights timeline via `hoveredCamera`); (03) severity donut (recharts `PieChart/Pie/Cell`) toggles `filters.severity`; (04) confidence histogram (5 fixed bands 0–20…80–100) toggles `filters.confidenceBand` (band = `min(4, floor(confidence/20))`).
  - Stats cards: window counts + delta vs `previousWindowCount`, latency p50/p95, sparklines from `timeBuckets` (`lib/sentinel-selectors.ts:180`; step counts 5/6/8 per range) and `makeTimeline` (`overview-time.ts:17`; same step counts).
  - `components/alert-history.tsx` uses `minuteHeatBuckets` (`lib/detection-types.ts:66`, 30-minute heat strip, minute buckets with critical sub-counts).
  - Everything is computed client-side from the ≤50-alert session buffer — statistics are session-scoped, not historical (footnote in `overview.tsx` says exactly this).
- **G-7 Operations floor plan is illustrative.** `GeoDashboard` (`components/geo-dashboard.tsx`) draws rooms/camera pins from static geometry; incident-to-room mapping data lives in the dead `lib/dashboard-data.ts` (camera ids `CAM-04/12/…` that do not match the live `CAM-01/02` sources).
- **G-8 Manifest theme-color drift.** `app/manifest.ts` uses `#0f172a` while the visual foundation is `#090c0e` (`--surface-0`, `app/layout.tsx` viewport `themeColor`).
- **G-9 SSE streams are unauthenticated.** `EventSource` cannot carry `X-API-Key`; `/alerts` and `/detections` are consumed without credentials while REST calls are key-guarded (`api-auth.ts`). Operator actions are gated (`AccessNotice`), reads are not.
- **G-10 Session-scoped data only.** No pagination/history API is consumed; reload loses all alerts (there is no "restore" path). The 50-alert cap (`sentinel-store.tsx:36`) silently drops older session alerts.
- **G-11 Repo hygiene.** `components/files.zip` / `files (1).zip`, `backend-sse.*.log`, `backend-test.*.log` at repo root, BOM-prefixed files (§2.3).

## 6. Validation actually run (this ticket, worktree `wt-02`)

| Command | Result |
|---|---|
| `npm ci` | exit 0 (untracked `node_modules` created in worktree) |
| `npm run typecheck` (`tsc --noEmit`) | **exit 0**, no diagnostics |
| `npm run lint` (`eslint components app lib hooks`) | **exit 0**, no diagnostics |
| `node scripts/docs-contract.mjs --check` (baseline, before these files existed) | **exit 1** — exact output: `Stale generated document: docs/SOURCE-MANIFEST.json` / `Stale generated document: docs/CURRENT.md` |
| `node scripts/docs-contract.mjs --check` (after adding `docs/blueprint/design-map.md` + `ui-contract.md`) | **exit 1** — exact output: `Unregistered active document: docs/blueprint/design-map.md` / `Unregistered active document: docs/blueprint/ui-contract.md` / `Stale generated document: docs/SOURCE-MANIFEST.json` / `Stale generated document: docs/CURRENT.md` |

Docs-checker failure analysis (checker **not** modified; rules **not** deleted):

- `Stale generated document: docs/SOURCE-MANIFEST.json` / `docs/CURRENT.md` is **pre-existing at the pinned baseline**: `scripts/docs_contract.py` `generate()` regenerates those files from the registered evidence report (`bench/results/sprint2-verified-480p/report.json`) and compares; the pinned source hashes no longer match the registered report, so `--check` fails before any file of this ticket exists. Fixing it is a `npm run docs:sync` + evidence decision owned by the orchestrator, not this read-only inventory ticket.
- `Unregistered active document` is produced by `check_policy()` (`scripts/docs_contract.py:116`): every `docs/**/*.md` must appear in `docs/authority.json` → `canonical_docs` (currently only the 6 status docs: `CURRENT`, `PLAN`, `DESIGN`, `ISSUES`, `RUNBOOK`, `MAINTENANCE`). Both new blueprint files therefore fail the policy check. Remediation is outside this ticket's write scope (`docs/blueprint/`, `docs/campaign/` only): the orchestrator must either add these paths to the policy's allowlist — ideally via a scoped/non-authority allowlist rather than promoting scoped inventories into `canonical_docs`, since the campaign contract states such catalogs "must not become status/design authority" — or extend the policy schema. Do **not** force success by deleting check rules or retirement records.

Not run (out of scope for this read-only inventory ticket): browser rendering, e2e (`tests/e2e/test_operator_flows.py`), backend-dependent flows. All browser-dependent statements are marked **[UNVERIFIED — browser]**.
