import type { LiveAlert } from "@/components/video-player"

export type Range = "15m" | "1h" | "24h" | "all"
export type CrossFilters = {
  cameraId?: string
  type?: LiveAlert["type"]
  severity?: LiveAlert["severity"]
  confidenceBand?: number
  range: Range
}

/* ── WT-25 additive: single-source severity vocabulary ─────────────────────────
   Every surface that renders a severity imports these maps instead of keeping a
   private copy (the baseline had eight copies: alert-feed, alert-history,
   alert-toast, incident-panel, incidents-section, category-filter,
   ui-intel-ops-section, geo-dashboard). */

export const SEVERITY_LABEL: Record<LiveAlert["severity"], string> = {
  critical: "حرج",
  high: "مرتفع",
  medium: "متوسط",
}

export const SEVERITY_TOKEN: Record<LiveAlert["severity"], string> = {
  critical: "var(--threat-critical)",
  high: "var(--threat-high)",
  medium: "var(--threat-medium)",
}

/** Triage ordering: critical first, newest first inside a tier. */
export const SEVERITY_ORDER: Record<LiveAlert["severity"], number> = {
  critical: 0,
  high: 1,
  medium: 2,
}

/** The producer can emit "none"/"low" (`backend/decision_config.py:83-84`); the
 *  alert contract has no such tier, and dropping a confirmed alert silently is
 *  worse than showing it at the lowest displayable severity (runtime risk R-3).
 *  Anything else remains rejected. */
export function normalizeSeverity(value: unknown): LiveAlert["severity"] | null {
  if (value === "critical" || value === "high" || value === "medium") return value
  if (value === "none" || value === "low") return "medium"
  return null
}

export function compareBySeverity(
  a: Pick<LiveAlert, "severity" | "isoTime">,
  b: Pick<LiveAlert, "severity" | "isoTime">,
): number {
  const rank = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
  if (rank !== 0) return rank
  return Date.parse(b.isoTime) - Date.parse(a.isoTime)
}

/* ── WT-25 additive: incident triage state machine ────────────────────────────
   WT-11 T25-1: جديد → قيد المعالجة → مُعلَّق → مُغلق, with the actor and
   timestamp recorded for every transition. Acknowledging an alert is the
   `new → in_progress` transition (its action verb is kept in the record). */

export type TriageState = "new" | "in_progress" | "on_hold" | "resolved"
export type TriageAction = "acknowledge" | "hold" | "resume" | "resolve" | "reopen"
export type TriageSource = "server" | "session"
export type TriageHistoryEntry = { action: TriageAction; actor: string; at: number }
export type TriageRecord = {
  state: TriageState
  action: TriageAction
  actor: string
  at: number
  source: TriageSource
  /** Bounded transition log, oldest first (server keeps the last 20). */
  history: TriageHistoryEntry[]
}

export const TRIAGE_STATES: readonly TriageState[] = ["new", "in_progress", "on_hold", "resolved"]
export const TRIAGE_ACTIONS: readonly TriageAction[] = ["acknowledge", "hold", "resume", "resolve", "reopen"]

export const TRIAGE_LABEL: Record<TriageState, string> = {
  new: "جديد",
  in_progress: "قيد المعالجة",
  on_hold: "مُعلَّق",
  resolved: "مُغلق",
}

export const TRIAGE_ACTION_LABEL: Record<TriageAction, string> = {
  acknowledge: "استلام",
  hold: "تعليق",
  resume: "استئناف",
  resolve: "إغلاق",
  reopen: "إعادة فتح",
}

export const TRIAGE_ALLOWED: Record<TriageState, readonly TriageAction[]> = {
  new: ["acknowledge", "resolve"],
  in_progress: ["hold", "resolve"],
  on_hold: ["resume", "resolve"],
  resolved: ["reopen"],
}

/** Returns the next state, or null when the transition is not allowed. */
export function reduceTriage(state: TriageState, action: TriageAction): TriageState | null {
  if (!TRIAGE_ALLOWED[state].includes(action)) return null
  switch (action) {
    case "acknowledge":
    case "resume":
    case "reopen":
      return "in_progress"
    case "hold":
      return "on_hold"
    case "resolve":
      return "resolved"
  }
}

export const INITIAL_TRIAGE: TriageRecord = { state: "new", action: "acknowledge", actor: "", at: 0, source: "session", history: [] }

export const TRIAGE_MAX_TRACKED = 200
const TRIAGE_HISTORY_LIMIT = 20
export const UNKNOWN_ACTOR_LABEL = "غير معروف"

/** Session-side transition: applies `action` to the stored record and appends
 *  the actor + timestamp to the bounded activity log. Returns null when the
 *  transition is not allowed. */
export function triageActionRecord(
  previous: TriageRecord | undefined,
  action: TriageAction,
  actor: string,
  at: number,
): TriageRecord | null {
  const next = reduceTriage(previous?.state ?? "new", action)
  if (next === null) return null
  const resolvedActor = actor.trim() || UNKNOWN_ACTOR_LABEL
  return {
    state: next,
    action,
    actor: resolvedActor,
    at,
    source: "session",
    history: [...(previous?.history ?? []), { action, actor: resolvedActor, at }].slice(-TRIAGE_HISTORY_LIMIT),
  }
}

/** Newest record wins; the tracked map stays bounded. */
export function mergeTriageRecord(
  map: Record<string, TriageRecord>,
  alertId: string,
  record: TriageRecord,
): Record<string, TriageRecord> {
  const previous = map[alertId]
  if (previous && previous.at > record.at) return map
  return Object.fromEntries(Object.entries({ ...map, [alertId]: record }).slice(-TRIAGE_MAX_TRACKED))
}

const TRIAGE_STATE_LOOKUP: Record<string, true> = { new: true, in_progress: true, on_hold: true, resolved: true }
const TRIAGE_ACTION_LOOKUP: Record<string, true> = { acknowledge: true, hold: true, resume: true, resolve: true, reopen: true }

/** Parses a triage record from the API (`GET/POST /alerts/{id}/triage`) or an
 *  `alert_triage` SSE frame. Fail-closed: unknown states/actions are rejected. */
export function parseTriageRecord(value: unknown): TriageRecord | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const raw = value as Record<string, unknown>
  if (typeof raw.state !== "string" || TRIAGE_STATE_LOOKUP[raw.state] !== true) return null
  if (typeof raw.action !== "string" || TRIAGE_ACTION_LOOKUP[raw.action] !== true) return null
  const at = typeof raw.at === "string" ? Date.parse(raw.at) : typeof raw.at === "number" ? raw.at : NaN
  if (!Number.isFinite(at)) return null
  const actor = boundedString(raw.actor, 64) ? (raw.actor as string) : "غير معروف"
  const source: TriageSource = raw.source === "session" ? "session" : "server"
  const history: TriageHistoryEntry[] = Array.isArray(raw.history)
    ? raw.history.flatMap((entry): TriageHistoryEntry[] => {
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) return []
      const item = entry as Record<string, unknown>
      if (typeof item.action !== "string" || TRIAGE_ACTION_LOOKUP[item.action] !== true) return []
      const entryAt = typeof item.at === "string" ? Date.parse(item.at) : typeof item.at === "number" ? item.at : NaN
      if (!Number.isFinite(entryAt)) return []
      const entryActor = boundedString(item.actor, 64) ? (item.actor as string) : "غير معروف"
      return [{ action: item.action as TriageAction, actor: entryActor, at: entryAt }]
    }).slice(-20)
    : []
  return { state: raw.state as TriageState, action: raw.action as TriageAction, actor, at, source, history }
}

/** `type: "alert_triage"` frames on the alert stream (additive event). */
export function parseTriageEnvelope(data: unknown): { alertId: string; record: TriageRecord } | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null
  const raw = data as Record<string, unknown>
  if (raw.type !== "alert_triage" || typeof raw.alertId !== "string" || !ALERT_ID_PATTERN.test(raw.alertId)) return null
  const record = parseTriageRecord(raw.triage)
  return record ? { alertId: raw.alertId, record } : null
}

/** Demo/file sources are named `EXAMPLE-…` by the backend demo routes
 *  (`/demo_start/{EXAMPLE-0x}`); their alerts are replays, never live capture. */
export const REPLAY_SOURCE_PREFIX = "EXAMPLE-"

/** Frames that legitimately share the `/alerts` stream and are not alerts. */
const NON_ALERT_FRAME_TYPES: Record<string, true> = { person_detection: true, VLM_Report: true, alert_triage: true }

export type StreamFrame =
  | { kind: "alert"; alert: LiveAlert }
  | { kind: "triage"; alertId: string; record: TriageRecord }
  | { kind: "person"; count: number }
  | { kind: "ignored" }
  | { kind: "rejected" }

/** Classifies one `/alerts` SSE frame. Alert-shaped frames that fail validation
 *  are surfaced as `rejected` so the drop is visible in the UI (no silent loss). */
export function parseStreamFrame(raw: string): StreamFrame {
  let data: unknown
  try { data = JSON.parse(raw) } catch { return { kind: "rejected" } }
  const triage = parseTriageEnvelope(data)
  if (triage) return { kind: "triage", alertId: triage.alertId, record: triage.record }
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const frame = data as Record<string, unknown>
    if (frame.type === "person_detection") {
      const count = parsePersonCountEnvelope(data)
      return count === null ? { kind: "ignored" } : { kind: "person", count }
    }
    if (NON_ALERT_FRAME_TYPES[String(frame.type)] !== true && typeof frame.id === "string") {
      const alert = parseAlertEnvelope(data)
      return alert ? { kind: "alert", alert } : { kind: "rejected" }
    }
  }
  return { kind: "ignored" }
}

const RANGE_MS: Record<Exclude<Range, "all">, number> = {
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "24h": 24 * 60 * 60_000,
}

const ALERT_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/
const ISO_TIMESTAMP_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/
const MIN_LATENCY_SAMPLES = 2

function boundedString(value: unknown, maxLength: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= maxLength
}

function optionalPercent(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100
    ? value : undefined
}

function optionalNonNegative(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value : undefined
}

function optionalSafeInteger(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value : undefined
}

function optionalLabels(value: unknown): string[] | undefined {
  if (!Array.isArray(value) || value.length > 32
    || !value.every((label) => boundedString(label, 80))) return undefined
  return value.map((label) => label.trim()).filter(Boolean)
}

function optionalProbability(value: unknown): number | null | undefined {
  if (value === null) return null
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1 ? value : undefined
}

function optionalBox(value: unknown): [number, number, number, number] | undefined {
  if (!Array.isArray(value) || value.length !== 4
    || !value.every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate) && coordinate >= 0)
    || value[2] <= value[0] || value[3] <= value[1]) return undefined
  return [value[0], value[1], value[2], value[3]]
}

/** Accept the established SSE envelope and normalize the backend's weapon label. */
export function parseAlertEnvelope(data: unknown): LiveAlert | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null
  const value = data as Record<string, unknown>
  // R-3: the producer ranks severity with `severity_for`, which can return
  // "none"/"low"; normalize those to the lowest displayable tier rather than
  // silently dropping a confirmed alert.
  const severity = normalizeSeverity(value.severity)
  if (value.confirmedAlert !== undefined && value.confirmedAlert !== true) return null
  if (value.alertState !== undefined && value.alertState !== "CONFIRMED") return null
  if (typeof value.id !== "string" || !ALERT_ID_PATTERN.test(value.id)
    || !boundedString(value.cameraId, 128)
    || !["Violence", "Weapon", "Weapon Detection"].includes(String(value.type))
    || severity === null
    || optionalPercent(value.confidence) === undefined
    || !boundedString(value.timestamp, 64)
    || !boundedString(value.isoTime, 64) || !ISO_TIMESTAMP_PATTERN.test(value.isoTime)
    || !Number.isFinite(Date.parse(value.isoTime))
    || !boundedString(value.location, 512)) return null

  const alert: LiveAlert = {
    id: value.id,
    cameraId: value.cameraId,
    severity,
    type: value.type === "Weapon Detection" ? "Weapon" : value.type as LiveAlert["type"],
    confidence: value.confidence as number,
    timestamp: value.timestamp,
    isoTime: value.isoTime,
    location: value.location,
  }

  const modelConfidence = optionalPercent(value.modelConfidence)
  const rawModelConfidence = optionalProbability(value.rawModelConfidence)
  const threatConfidence = optionalPercent(value.threatConfidence)
  const fusionScore = optionalPercent(value.fusionScore)
  const motionScore = optionalPercent(value.motionScore)
  const weaponScore = optionalPercent(value.weaponScore)
  const alertLatencyMs = optionalNonNegative(value.alertLatencyMs)
  const personCount = optionalSafeInteger(value.personCount)
  const fusionModel = boundedString(value.fusionModel, 120) ? value.fusionModel : undefined
  const fusionReason = boundedString(value.fusionReason, 512) ? value.fusionReason : undefined
  const weaponLabels = optionalLabels(value.weaponLabels)
  const clipUrl = boundedString(value.clipUrl, 2048) ? value.clipUrl : undefined
  const weaponDetectorReady = typeof value.weaponDetectorReady === "boolean" ? value.weaponDetectorReady : undefined
  const threatType = value.threatType === "violence" || value.threatType === "weapon" ? value.threatType : undefined

  if (modelConfidence !== undefined) alert.modelConfidence = modelConfidence
  if (rawModelConfidence !== undefined) alert.rawModelConfidence = rawModelConfidence
  if (threatConfidence !== undefined) alert.threatConfidence = threatConfidence
  if (fusionScore !== undefined) alert.fusionScore = fusionScore
  if (motionScore !== undefined) alert.motionScore = motionScore
  if (weaponScore !== undefined) alert.weaponScore = weaponScore
  if (alertLatencyMs !== undefined) alert.alertLatencyMs = alertLatencyMs
  if (personCount !== undefined) alert.personCount = personCount
  if (fusionModel !== undefined) alert.fusionModel = fusionModel
  if (fusionReason !== undefined) alert.fusionReason = fusionReason
  if (weaponLabels !== undefined) alert.weaponLabels = weaponLabels
  if (clipUrl !== undefined) alert.clipUrl = clipUrl
  if (weaponDetectorReady !== undefined) alert.weaponDetectorReady = weaponDetectorReady
  if (threatType !== undefined) alert.threatType = threatType
  const rawScore = optionalProbability(value.rawModelScore)
  if (rawScore !== undefined) alert.rawModelScore = rawScore
  if (["violence", "weapon", "unknown"].includes(String(value.scoreSource))) {
    alert.scoreSource = value.scoreSource as LiveAlert["scoreSource"]
  }
  const calibrated = optionalProbability(value.calibratedProbability)
  if (value.calibrationStatus !== undefined || value.calibratedProbability !== undefined) {
    const applicable = (value.calibrationStatus === "calibrated" || value.calibrationStatus === "calibrated-candidate")
      && typeof calibrated === "number"
    alert.calibrationStatus = applicable ? value.calibrationStatus as string : "unverified"
    alert.calibratedProbability = applicable ? calibrated : null
  }
  if (value.scoreSemantics && typeof value.scoreSemantics === "object" && !Array.isArray(value.scoreSemantics)) {
    const semantics = Object.entries(value.scoreSemantics)
    if (semantics.length <= 16 && semantics.every(([key, text]) => /^[A-Za-z][A-Za-z_]{0,63}$/.test(key) && boundedString(text, 512))) {
      alert.scoreSemantics = Object.fromEntries(semantics) as Record<string, string>
    }
  }
  if (boundedString(value.severitySource, 160)) alert.severitySource = value.severitySource
  if (value.confirmedAlert === true) alert.confirmedAlert = true
  if (value.alertState === "CONFIRMED") alert.alertState = "CONFIRMED"
  const weaponBbox = optionalBox(value.weaponBbox)
  const violenceBbox = optionalBox(value.violenceBbox)
  if (weaponBbox) alert.weaponBbox = weaponBbox
  if (violenceBbox) alert.violenceBbox = violenceBbox
  const width = optionalSafeInteger(value.alertVideoWidth)
  const height = optionalSafeInteger(value.alertVideoHeight)
  if (width !== undefined && width > 0) alert.alertVideoWidth = width
  if (height !== undefined && height > 0) alert.alertVideoHeight = height
  return alert
}

export function parsePersonCountEnvelope(data: unknown): number | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null
  const value = data as Record<string, unknown>
  return value.type === "person_detection" && typeof value.personCount === "number"
    && Number.isSafeInteger(value.personCount) && value.personCount >= 0
    ? value.personCount : null
}

export function selectVisibleAlerts(alerts: readonly LiveAlert[], filters: CrossFilters, now = Date.now()): LiveAlert[] {
  const cutoff = filters.range === "all" ? -Infinity : now - RANGE_MS[filters.range]
  return alerts.filter((alert) => {
    const time = Date.parse(alert.isoTime)
    return Number.isFinite(time) && time >= cutoff && time <= now
      && (!filters.cameraId || alert.cameraId === filters.cameraId)
      && (!filters.type || alert.type === filters.type)
      && (!filters.severity || alert.severity === filters.severity)
      && (filters.confidenceBand === undefined || Math.min(4, Math.floor(alert.confidence / 20)) === filters.confidenceBand)
  })
}

export function countBy<T extends string>(alerts: readonly LiveAlert[], key: (alert: LiveAlert) => T): Record<T, number> {
  return alerts.reduce((counts, alert) => {
    const value = key(alert)
    const next = Object.prototype.hasOwnProperty.call(counts, value) ? counts[value] + 1 : 1
    Object.defineProperty(counts, value, { value: next, configurable: true, enumerable: true, writable: true })
    return counts
  }, {} as Record<T, number>)
}

export const countsByType = (alerts: readonly LiveAlert[]) => countBy(alerts, (alert) => alert.type)
export const countsBySeverity = (alerts: readonly LiveAlert[]) => countBy(alerts, (alert) => alert.severity)
export const countsByCamera = (alerts: readonly LiveAlert[]) => countBy(alerts, (alert) => alert.cameraId)

function percentile(values: number[], fraction: number): number | null {
  if (values.length === 0) return null
  const index = (values.length - 1) * fraction
  const lower = Math.floor(index)
  const upper = Math.ceil(index)
  return Math.round(values[lower] + (values[upper] - values[lower]) * (index - lower))
}

export function latencyPercentiles(alerts: readonly LiveAlert[]): { p50: number | null; p95: number | null } {
  const samples = alerts.map((alert) => alert.alertLatencyMs)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0)
    .sort((a, b) => a - b)
  if (samples.length < MIN_LATENCY_SAMPLES) return { p50: null, p95: null }
  return { p50: percentile(samples, .5), p95: percentile(samples, .95) }
}

export function selectThreatLevel(alerts: readonly LiveAlert[], now = Date.now()): "critical" | "high" | "calm" {
  const recent = alerts.filter((alert) => {
    const time = Date.parse(alert.isoTime)
    return Number.isFinite(time) && time <= now && time >= now - RANGE_MS["15m"]
  })
  if (recent.some((alert) => alert.severity === "critical")) return "critical"
  if (recent.some((alert) => alert.severity === "high")) return "high"
  return "calm"
}

export function timeBuckets(alerts: readonly LiveAlert[], filters: CrossFilters, now = Date.now()) {
  const oldest = alerts.length ? Math.min(...alerts.map((alert) => Date.parse(alert.isoTime))) : now
  const duration = filters.range === "15m" ? 15 * 60_000 : filters.range === "1h" ? 60 * 60_000 : filters.range === "24h" ? 24 * 60 * 60_000 : Math.max(60 * 60_000, now - oldest + 1)
  const steps = filters.range === "15m" ? 5 : filters.range === "1h" ? 6 : 8
  const size = duration / steps
  const start = now - duration
  const buckets = Array.from({ length: steps }, (_, index) => ({
    label: new Date(start + size * (index + 1)).toLocaleTimeString("ar-SA", { hour: "2-digit", minute: "2-digit" }),
    Weapon: 0,
    Violence: 0,
  }))
  for (const alert of alerts) {
    const time = Date.parse(alert.isoTime)
    if (!Number.isFinite(time) || time < start || time > now) continue
    const index = Math.min(steps - 1, Math.floor((time - start) / size))
    if (index >= 0 && index < buckets.length) buckets[index][alert.type]++
  }
  return buckets
}

export function confidenceHistogram(alerts: readonly LiveAlert[]) {
  const buckets = ["0–20", "20–40", "40–60", "60–80", "80–100"].map((label) => ({ label, count: 0 }))
  for (const alert of alerts) {
    // The event contract reports confidence on a 0–100 scale.
    if (alert.confidence >= 0 && alert.confidence <= 100) {
      buckets[Math.min(4, Math.floor(alert.confidence / 20))].count++
    }
  }
  return buckets
}

export function previousWindowCount(alerts: readonly LiveAlert[], filters: CrossFilters, now = Date.now()): number | null {
  if (filters.range === "all") return null
  const duration = RANGE_MS[filters.range]
  return alerts.filter((alert) => {
    const time = Date.parse(alert.isoTime)
    return time >= now - duration * 2 && time < now - duration
      && (!filters.cameraId || alert.cameraId === filters.cameraId)
      && (!filters.type || alert.type === filters.type)
      && (!filters.severity || alert.severity === filters.severity)
      && (filters.confidenceBand === undefined || Math.min(4, Math.floor(alert.confidence / 20)) === filters.confidenceBand)
  }).length
}

/* ── WT-26 additive statistics semantics (flagged hunks — nothing above changed) ──
   Precise counting/window semantics for the overview slice; see
   docs/campaign/engineering/26-stats-semantics.md §5 (D1–D9). */

/** Mirrors the reducer cap in lib/sentinel-store.tsx (`slice(0, 50)`). If the
 *  store cap ever changes, this constant must change with it (flagged drift). */
export const SESSION_ALERT_CAP = 50

export type Interval = { from: number; to: number }

export type SessionCoverage = {
  observedFrom: number | null
  observedTo: number | null
  capped: boolean
}

/** What this browser session actually observed: a contiguous recency suffix of
 *  received alerts (newest SESSION_ALERT_CAP kept). `capped` means older alerts
 *  were evicted and any window starting before `observedFrom` is partially
 *  unobserved. */
export function sessionCoverage(alerts: readonly LiveAlert[], cap = SESSION_ALERT_CAP): SessionCoverage {
  let observedFrom: number | null = null
  let observedTo: number | null = null
  for (const alert of alerts) {
    const time = Date.parse(alert.isoTime)
    if (!Number.isFinite(time)) continue
    if (observedFrom === null || time < observedFrom) observedFrom = time
    if (observedTo === null || time > observedTo) observedTo = time
  }
  return { observedFrom, observedTo, capped: alerts.length >= cap }
}

/** Band index for a 0–100 threat-confidence score: min(4, floor(score / 20)).
 *  Parity with `confidenceHistogram` / `selectVisibleAlerts` banding. */
export function confidenceBandIndex(confidence: number): number {
  return Math.min(4, Math.floor(confidence / 20))
}

export type PreviousWindowComparison =
  | { available: true; previousCount: number; window: Interval }
  | { available: false; reason: "all-range" | "outside-session-coverage" | "empty-session" }

/** Comparison baseline for the "عن الفترة السابقة" delta, with two honesty
 *  rules that `previousWindowCount` alone cannot express:
 *  (1) brush parity — when a custom brush window is active, the baseline is the
 *      same window shifted back by one range duration (closed interval, like
 *      the brush filter itself); without a brush it is the half-open window
 *      [now-2d, now-d), matching `previousWindowCount`;
 *  (2) coverage — the baseline is refused when the session did not observe the
 *      whole baseline window (`observedFrom > window.from`), because session
 *      start or the 50-alert cap truncated it. */
export function previousWindowComparison(
  alerts: readonly LiveAlert[],
  filters: CrossFilters,
  now: number,
  brush: Interval | null = null,
): PreviousWindowComparison {
  if (filters.range === "all") return { available: false, reason: "all-range" }
  if (alerts.length === 0) return { available: false, reason: "empty-session" }
  const duration = RANGE_MS[filters.range]
  const window: Interval = brush
    ? { from: brush.from - duration, to: brush.to - duration }
    : { from: now - duration * 2, to: now - duration }
  const coverage = sessionCoverage(alerts)
  if (coverage.observedFrom === null || coverage.observedFrom > window.from) {
    return { available: false, reason: "outside-session-coverage" }
  }
  const previousCount = alerts.filter((alert) => {
    const time = Date.parse(alert.isoTime)
    const inWindow = brush ? time >= window.from && time <= window.to : time >= window.from && time < window.to
    return Number.isFinite(time) && inWindow
      && (!filters.cameraId || alert.cameraId === filters.cameraId)
      && (!filters.type || alert.type === filters.type)
      && (!filters.severity || alert.severity === filters.severity)
      && (filters.confidenceBand === undefined || confidenceBandIndex(alert.confidence) === filters.confidenceBand)
  }).length
  return { available: true, previousCount, window }
}

export type ChartDimensionSets = {
  camera: LiveAlert[]
  severity: LiveAlert[]
  confidence: LiveAlert[]
  timeline: LiveAlert[]
  context: LiveAlert[]
}

/** Cross-filter isolation for the four overview panels (design-map G-6): each
 *  chart drops its own dimension so its distribution stays readable while all
 *  other filters apply. The brush applies to camera/severity/confidence but
 *  never to the timeline (the brush must stay legible over stable data) nor to
 *  the context probe (range only). */
export function chartDimensionSets(
  alerts: readonly LiveAlert[],
  filters: CrossFilters,
  now: number,
  brush: Interval | null = null,
): ChartDimensionSets {
  const inBrush = (alert: LiveAlert) => {
    if (!brush) return true
    const time = Date.parse(alert.isoTime)
    return Number.isFinite(time) && time >= brush.from && time <= brush.to
  }
  const select = (without: "cameraId" | "severity" | "confidenceBand") =>
    selectVisibleAlerts(alerts, { ...filters, [without]: undefined }, now).filter(inBrush)
  return {
    camera: select("cameraId"),
    severity: select("severity"),
    confidence: select("confidenceBand"),
    timeline: selectVisibleAlerts(alerts, { ...filters, cameraId: undefined, type: undefined }, now),
    context: selectVisibleAlerts(alerts, { range: filters.range }, now),
  }
}
