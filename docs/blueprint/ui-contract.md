---
authority: scoped
non_authoritative: true
---
# AI Sentinel — shared UI data contracts (ui-contract)

Campaign ticket WT-02. Worktree `wt-02`, branch `codex/sentinel-02-design-map`, baseline `e86d34b`.
Companion to `docs/blueprint/design-map.md` (feature IDs `U-01`…`U-10`, renumbered from the map's original `F-01`…`F-10` in the blueprint seed so `F-01`…`F-49` stay reserved for runtime features; see `docs/blueprint/index.json`).

> **SHARED CONTRACT — orchestrator coordination required.** Every type below is consumed by more than one surface and/or crosses the backend↔frontend boundary. Changing any of them is a cross-workstream event: the parse functions in `lib/` are the single normalization point, backend producers (`backend/api.py` and pipeline modules) own the wire format, and UI consumers (U-01…U-07) own presentation. Do not fork these shapes into a component; extend here and in `lib/` first.

All types are quoted from source at baseline. Wire formats are whatever the parser functions accept (they are deliberately tolerant: snake_case and camelCase aliases, clamped ranges, fail-closed on malformed data).

## C-1 Alert payload (SSE `GET /alerts`) — `LiveAlert`

Defined at `components/video-player.tsx:47` (the de-facto domain type, imported by nearly every component); parsed by `parseAlertEnvelope` (`lib/sentinel-selectors.ts:47`) and `parsePersonCountEnvelope` (`lib/sentinel-selectors.ts:104`); dispatched by `lib/sentinel-store.tsx`.

```ts
export interface LiveAlert {
  id: string                       // /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/ (parser-enforced)
  timestamp: string                // display string, bounded ≤64 chars
  isoTime: string                  // full ISO with zone, /^\d{4}-…(Z|[+-]\d{2}:\d{2})$/, must parse
  confidence: number               // 0–100 (percent scale — see parser comment)
  modelConfidence?: number         // 0–100
  rawModelConfidence?: number      // 0–100
  threatConfidence?: number        // 0–100
  type: "Violence" | "Weapon"      // wire may say "Weapon Detection" → normalized to "Weapon"
  severity: "critical" | "high" | "medium"
  cameraId: string                 // ≤128 chars
  location: string                 // ≤512 chars
  fusionScore?: number             // 0–100
  fusionModel?: string             // ≤120 chars
  motionScore?: number             // 0–100
  weaponScore?: number             // 0–100
  weaponLabels?: string[]          // ≤32 entries, each ≤80 chars, trimmed/deduped at use
  weaponDetectorReady?: boolean
  fusionReason?: string            // ≤512 chars
  faceSummary?: FaceSummaryPayload
  clipUrl?: string                 // ≤2048 chars
  categories?: CategoryScore[]
  primaryCategory?: DetectionCategory
  allCategories?: DetectionCategory[]
  threatType?: "violence" | "weapon"
  alertLatencyMs?: number          // ≥0
  personCount?: number             // safe integer ≥0
  weaponBbox?: [number, number, number, number]
  violenceBbox?: [number, number, number, number]
  alertVideoWidth?: number
  alertVideoHeight?: number
}
```

Companion envelope on the same stream:

```ts
// type: "person_detection" messages (lib/sentinel-selectors.ts:104)
{ type: "person_detection"; personCount: number }  // safe integer ≥0
```

Related types (`components/video-player.tsx:20–44`, `lib/detection-types.ts`):

```ts
export interface FaceObservation {
  id: string; label: string; kind: "known" | "unknown"; confidence: number; bbox: number[]
}
export interface FaceUnknownDetail {
  id: string; firstSeenFrame: number; lastSeenFrame: number; durationFrames: number
  firstSeenAt: string; lastSeenAt: string; hitStreak: number; lastBbox: number[]
}
export interface FaceSummaryPayload {
  enabled: boolean
  identityLabelingEnabled?: boolean
  frameIndex?: number
  totalFaces: number
  recognized: Array<{ personId?: string; label?: string; confidence?: number; distance?: number }>
  recognizedCount?: number
  unknownIds: string[]
  unknownCount: number
  unknownDetails?: FaceUnknownDetail[]
  observations?: FaceObservation[]
}
export type DetectionCategory = "violence" | "weapon" | "crowd_surge" | "fall" | "intrusion" | "loitering"
export interface CategoryScore {
  category: DetectionCategory
  score: number
  threshold: number
  triggered: boolean
  severity: "low" | "medium" | "high" | "critical"
}
```

Notes:
- `faceSummary` is consumed by `components/incident-panel.tsx` (validated field-by-field: `totalFaces`, `unknownCount`, `recognizedCount`/`recognized.length` must be finite ≥0 to display).
- `categories`/`primaryCategory`/`allCategories` are declared on `LiveAlert` but no current parse path fills them from the SSE envelope (parser does not read them) — treat as reserved.

## C-2 Detection telemetry payload (SSE `GET /detections?camera_id=…`) — `PipelineTelemetry`

Defined `lib/pipeline-telemetry.ts:1`; parsed by `parseTelemetry(value, cameraId)` (`lib/pipeline-telemetry.ts:56`); consumed by `hooks/use-detection-stream.ts`, `components/pipeline-telemetry.tsx`, `components/video-player.tsx` (U-02/U-03).

```ts
export type DecisionState = "NORMAL" | "WATCH" | "CONFIRMED" | "COOLDOWN"
export type TelemetryHealth = { status: string; reason: string }

export type PipelineTelemetry = {
  cameraId: string
  sourceKind: "live" | "file" | null
  updatedAt: number | null          // epoch ms (wire: ISO string or epoch seconds)
  sequence: number | null           // inference sequence (wire: inferenceSequence|inference_sequence)
  violenceSequence: number | null   // wire: violenceSequence|violence_observation_id
  weaponSequence: number | null     // wire: weaponSequence|weapon_observation_id
  violenceScore: number | null      // probability 0–1 (nulled when stale)
  weaponScore: number | null        // probability 0–1 (nulled when stale)
  decisionState: DecisionState | null   // wire CONFIRMED_VIOLENCE → "CONFIRMED"
  confirmThreshold: number | null   // 0–1 (wire: decision.confirmThreshold|confirm_threshold)
  watchThreshold: number | null     // 0–1
  weaponThreshold: number | null    // 0–1
  confirmN: number | null
  confirmM: number | null
  rollingWindowCount: number | null
  cooldownRemainingSeconds: number | null
  framesCollected: number | null    // wire: window.framesCollected
  framesRequired: number | null     // wire: window.framesRequired
  windowSpanSeconds: number | null  // wire: window.spanSeconds|window_span_seconds
  windowValid: boolean | null       // wire: window.valid
  windowClockSource: "file-media" | "monotonic-capture" | null
  latencyMs: number | null
  calibrationStatus: string | null  // wire: calibrationStatus|decision.calibrationStatus|calibration_status
  health: Record<string, TelemetryHealth>  // keys read: capture, violence, weapon, person, decision, render
}
```

Wire aliases accepted by `parseTelemetry`: top-level `cameraId`, `sourceKind`, `updatedAt`, `latencyMs`, `violenceScore`, `weaponScore`; `decision` or `decision_layer` object; `window` object; `health` or `pipeline_health` object. Health items require `status: string` and optional `reason` (clamped 240 chars); status is uppercased. A `cameraId` mismatch drops the message (`parseTelemetry` returns `null`).

Derived UI types:

```ts
export type TelemetryPoint = {
  sequence: number; time: number             // time = receipt epoch ms
  violence: number | null; weapon: number | null   // only set on fresh modality completions
  violenceSequence: number | null; weaponSequence: number | null
}
export type ModalityFreshness = {
  violenceSequence: number | null; weaponSequence: number | null
  violenceReceivedAt: number | null; weaponReceivedAt: number | null
}
```

Staleness contract (see design-map §4 chain C): `telemetryIsStale` >5 s, `inferenceIsStale` >5 s per completed-observation receipt, `applyModalityFreshness` nulls stale scores and rewrites `health[modality]` to `{status: "DEGRADED", reason: "No new <modality> completion received in the last 5 seconds"}`.

## C-3 Detection overlay envelope (same SSE message) — `DetectionOverlayEnvelope`

Defined `lib/detection-envelope.ts:4`; parsed by `parseDetectionOverlayEnvelope` (`lib/detection-envelope.ts:137`) — **fail-closed**: any malformed field rejects the whole envelope. Consumed by `components/canvas-overlay.tsx`, `components/video-player.tsx`, `lib/live-visual-state.ts` equality checks.

```ts
type DetectionTrack = {
  id: string                                  // ≤128 chars, non-empty
  bbox: [number, number, number, number]      // 0…1_000_000; normalized 0–1 or pixel coords
  confidence: number                          // 0–1
  color: [number, number, number]             // integer RGB 0–255
}

export type DetectionOverlayEnvelope = {
  tracks: DetectionTrack[]                    // ≤256
  personCount: number                         // safe integer ≥0 (default 0)
  isThreat: boolean                           // default false
  threatConfidence: number                    // 0–100 (default 0)
  fps: number                                 // 0–1000 (default 0)
  weaponScore?: number                        // 0–100
  videoWidth?: number                         // 1…65_536; wire 0 → undefined (default 1280 applied downstream)
  videoHeight?: number                        // 1…65_536; wire 0 → undefined (default 720 downstream)
  multiThreat?: MultiThreatData
}

export interface ThreatBox {
  id: string                                  // ≤128 chars
  type: "violence" | "weapon"
  weaponType?: "gun" | "knife" | "explosive" | "unknown"
  bbox: [number, number, number, number]
  confidence: number                          // 0–1
  color: [number, number, number]
  label: string                               // ≤128 chars
}

export interface MultiThreatData {
  hasViolence: boolean
  hasWeapon: boolean
  isMultiThreat: boolean
  violenceScore: number                       // 0–100 (wire), default 0
  weaponScore: number                         // 0–100 (wire), default 0
  fusedScore: number                          // 0–100 (wire), default 0
  severity: "low" | "medium" | "high" | "critical"   // wire "none" → "medium"
  threatBoxes: ThreatBox[]                    // ≤256
  reason: string                              // ≤128 chars, default ""
}
```

Display normalization: `normalizeScoreToPercent` (`lib/live-visual-state.ts:113`) maps 0–1 or 0–100 scores to percent; `hasWeaponVisualSignal` (`:122`) is true for `multiThreat.hasWeapon` or normalized weapon score ≥30.

## C-4 Evidence item contracts

### C-4a Evidence chain ledger record — `EvidenceChainRecord`

Defined `lib/local-report.ts:14`; parsed by `parseEvidenceChainRecord(value, alertId)` (`lib/local-report.ts:33`) — validates hash format, `prevHash === "GENESIS"` allowed once, asset hashes `"N/A"` → `null`. Consumed by `components/incident-panel.tsx` (U-04). Served by `GET /evidence_chain/{alertId}`.

```ts
export type EvidenceChainRecord = {
  alertId: string
  timestamp: string                           // must Date.parse
  prevHash: string                            // "GENESIS" or /^[a-f0-9]{64}$/i
  currentHash: string                         // /^[a-f0-9]{64}$/i
  clipSha256: string | null                   // 64-hex or null ("N/A"/absent)
  snapshotSha256: string | null
  reportSha256: string | null
}
```

### C-4b Local evidence summary — `LocalEvidenceReport`

Defined `lib/local-report.ts:3`; parsed by `parseLocalEvidenceReport(value, alertId)` (`lib/local-report.ts:48`). Served by `GET /reports/local/{alertId}` (U-05 `AiReport`).

```ts
export type LocalEvidenceReport = {
  alertId: string                             // must equal requested id
  mode: "local-evidence-summary"              // literal
  report: string                              // non-empty, ≤100_000 chars
}
```

### C-4c Incident metric facts (derived, not wire)

`incidentEvidenceFacts(alert)` (`lib/local-report.ts:8`) — keeps "absent" distinct from observed zero:

```ts
{ fusion: number | null; weapon: number | null; motion: number | null
  latencyMs: number | null; weaponLabels: string[] }
```

### C-4d Folder clip listing — `GET /api/clips/list`

Parsed ad hoc by `parseClips` (`components/clip-sidebar.tsx:45`, U-04). Accepted shape:

```ts
{ clips: Array<{
    alertId: string          // /^[A-Za-z0-9_-]{1,128}$/
    clipUrl: string          // must equal "/clips/" + alertId exactly
    size: number             // finite ≥0 bytes
    mtime: number            // finite ≥0 epoch seconds
    timestamp?: string; cameraId?: string; type?: string
    confidence?: number      // 0–100
    severity?: "critical" | "high" | "medium"
  }> }
```

Playback source: `GET /clips/{alertId}` returns the video blob (auto-retried on 404 up to 10 × 2 s in `components/incident-replay.tsx:12–13`). Downloads: `GET /download_evidence/{alertId}` (HTTP 202 = still processing → poll), `GET /download_report/{alertId}`.

## C-5 Report fields (AI summary) — U-05

Not modeled as shared TS types; the contract is endpoint-level (`components/ai-report.tsx`):

| Endpoint | Method | Response contract as consumed |
|---|---|---|
| `/reports/local/{alertId}` | GET | 200 = body used as local summary; 404 = `missing`; 401/403 = reader-access required; other = error copy |
| `/reports/deepseek/status` | GET | `{ apiKeyPresent: boolean }` (nullable; drives "missing key" hint) |
| `/reports/deepseek/{alertId}` | GET | 200 body = model summary; failures → error state |
| `/reports/deepseek/{alertId}?force={bool}` | POST | regenerates summary (admin-gated server-side) |

`EvidenceStatus` (`components/incident-replay.tsx:12`) shared UI status union: `"unavailable" | "loading" | "ready" | "error"`.

## C-6 Operator access & system status (U-07) — shared state shapes

```ts
// hooks/use-api-access.ts
export type AccessState = "checking" | "unconfigured" | "required" | "verified" | "offline"

// GET /security/status  → { enabled: boolean }
// GET /security/session → { role?: string }   // "admin" | "viewer" observed in UI copy

// components/telegram-status.tsx (GET /system/status → data.notifications)
interface TelegramStatus {
  enabled: boolean
  ready?: boolean
  configured?: boolean
  lastSendStatus?: string | null
  lastError?: string | null
  lastSentAt?: string | null
  minAlertIntervalSeconds?: number
  provider?: string
  running: boolean
  min_severity?: string
}

// GET /health (components/sections/ui-intel-ops-section.tsx:74)
type Health = { health?: string; model?: { device?: string } }
```

Operator mutations (all via `apiFetch`, `X-API-Key` injected from `sessionStorage` key `ai-sentinel-api-key`, `lib/api-auth.ts`):

| Endpoint | Method | Body |
|---|---|---|
| `/set_threshold` | POST | `{ threshold: number }` (UI sends value/100 → 0–1) |
| `/set_cooldown` | POST | `{ cooldown: number }` (seconds) |
| `/demo_start/{EXAMPLE-0x}` | POST | — |
| `/demo_stop/{EXAMPLE-0x}` | DELETE | — |
| `/notifications/telegram/test` | POST | → `{ success?: boolean }` |

## C-7 Filter state (shared across U-01…U-07) — `CrossFilters`

Defined `lib/sentinel-selectors.ts:3`; stored once in `SentinelProvider` (`lib/sentinel-store.tsx`); every screen reads/writes the same object.

```ts
export type Range = "15m" | "1h" | "24h" | "all"
export type CrossFilters = {
  cameraId?: string
  type?: LiveAlert["type"]            // "Violence" | "Weapon"
  severity?: LiveAlert["severity"]    // "critical" | "high" | "medium"
  confidenceBand?: number             // 0..4 = 20-point band of confidence (0–100)
  range: Range                        // default "1h"
}
```

Confidence band rule (used by both filtering and the histogram): `band = min(4, floor(confidence / 20))`, `confidence` on the 0–100 scale (`lib/sentinel-selectors.ts:113,207`).

## C-8 Shared UI-state vocabulary (U-02/U-03/U-04) — `SourceVisualState`

```ts
// lib/live-visual-state.ts:3
export type SourceVisualState = "live" | "replay" | "stale" | "offline" | "loading" | "unverified"
```

Arabic labels and token colors must stay in sync across `ui-monitor-section.tsx` (`STATE_LABEL`/`STATE_COLOR`) and `video-player.tsx` (`STATE_COPY`/`STATE_TOKEN`) — a drift risk recorded in design-map §2.3; centralizing them is a candidate refactor but changes behavior surface, so it needs orchestrator sign-off.

## Coordination checklist for changes

1. Backend producer change → update parser in `lib/` first (fail-closed rules), then this file, then consumers.
2. `LiveAlert` / `PipelineTelemetry` / `DetectionOverlayEnvelope` changes touch U-01…U-04, `hooks/use-detection-stream.ts`, `lib/sentinel-store.tsx`, and the test files `tests/*.test.mjs` (`detection-envelope`, `pipeline-telemetry`, `visual-state`, `local-report`, `api-auth`).
3. `CrossFilters` changes touch every screen and the e2e cross-filter test (`tests/e2e/test_operator_flows.py::test_camera_cross_filter_updates_overview_incidents_and_clear`).
4. Wire-format fields not currently parsed (`categories`, `primaryCategory`, `allCategories`, `faceSummary` subfields beyond counts) are reserved — do not repurpose without a parser change.
