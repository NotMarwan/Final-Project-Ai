export type DetectionCategory = 
  | "violence"
  | "weapon"
  | "crowd_surge"
  | "fall"
  | "intrusion"
  | "loitering"

export type CategoryStatus = "active" | "experimental" | "unsupported";

export interface CategoryCapability {
  id: DetectionCategory;
  label: string;
  enabled: boolean;
  status: CategoryStatus;
  threshold: number;
  reason: string;
  requiredInputs: string[];
}

export interface CategoryConfig {
  violenceEnabled: boolean
  violenceThreshold: number
  weaponEnabled: boolean
  weaponThreshold: number
  crowdSurgeEnabled: boolean
  crowdSurgeThreshold: number
  fallEnabled: boolean
  fallThreshold: number
  intrusionEnabled: boolean
  intrusionThreshold: number
  loiteringEnabled: boolean
  loiteringThreshold: number
}

export interface CategoryScore {
  category: DetectionCategory
  score: number
  threshold: number
  triggered: boolean
  severity: "low" | "medium" | "high" | "critical"
}

export const CATEGORY_LABELS: Record<DetectionCategory, string> = {
  violence: "اعتداء",
  weapon: "سلاح",
  crowd_surge: "تدافع",
  fall: "سقوط",
  intrusion: "تسلل",
  loitering: "تسكع",
}

export const CATEGORY_COLORS: Record<DetectionCategory, string> = {
  violence: "text-[var(--cat-violence)] border-[var(--cat-violence)]",
  weapon: "text-[var(--cat-weapon)] border-[var(--cat-weapon)]",
  crowd_surge: "text-[var(--threat-high)] border-[var(--threat-high)]",
  fall: "text-[var(--signal)] border-[var(--signal)]",
  intrusion: "text-[var(--threat-critical)] border-[var(--threat-critical)]",
  loitering: "text-[var(--text-secondary)] border-[var(--text-secondary)]",
}

/* ── Severity / alert-type / range label authority (WT-26) ──────────────────
   Single source for the overview slice. Alert rows say "تنبيه" (alert), never
   "رصد" (detection) or "حادثة" (incident) — see docs/campaign/engineering/
   26-stats-semantics.md §1 for the vocabulary contract. */

export type SeverityKey = "critical" | "high" | "medium"
export type AlertTypeKey = "Weapon" | "Violence"

export const SEVERITY_LABELS: Record<SeverityKey, string> = {
  critical: "حرج",
  high: "مرتفع",
  medium: "متوسط",
}

/** Alert-level type labels (the counted unit is an alert, not a model read). */
export const ALERT_TYPE_LABELS: Record<AlertTypeKey, string> = {
  Weapon: "تنبيه سلاح",
  Violence: "تنبيه اعتداء",
}

/** Short axis/legend labels for aggregate counts of alerts by type. */
export const ALERT_TYPE_SHORT_LABELS: Record<AlertTypeKey, string> = {
  Weapon: "أسلحة",
  Violence: "اعتداءات",
}

/** Threat-confidence bands: index = min(4, floor(score / 20)), score 0–100. */
export const CONFIDENCE_BAND_LABELS = ["0–20", "20–40", "40–60", "60–80", "80–100"] as const

export const RANGE_LABELS = {
  "15m": "آخر 15 دقيقة",
  "1h": "آخر ساعة",
  "24h": "آخر 24 ساعة",
  all: "الجلسة (حد أقصى 50)",
} as const

/** Counting-semantics legend rendered under the overview statistics (S26-1). */
export const STATS_LEGEND: { term: string; definition: string }[] = [
  { term: "تنبيه", definition: "قرار رصد مؤكّد وصل عبر قناة التنبيهات بمعرّف فريد. هذا هو وحدة العدّ في كل الأرقام أعلاه." },
  { term: "كشف / قراءة نموذج", definition: "مخرَج نموذج لكل إطار (درجة، صندوق). لا يُعدّ في هذه اللوحة إطلاقاً؛ يظهر في البثّ التشغيلي فقط." },
  { term: "أشخاص ظاهرون", definition: "عدد الأشخاص في آخر إطار معالَج — قياس لحظي بلا فترة زمنية." },
  { term: "أشخاص متبَّعون فريدون خلال الفترة", definition: "غير متاح — لا يوجد مصدر بيانات يوفّر العدد (المصدر يرسل معرّفات التتبّع لكل إطار فقط ولا يخزّنها)." },
  { term: "زمن احتساب القرار", definition: "زمن معالجة الخادم لحظة بناء التنبيه — ليس زمن وصول التنبيه للمشغّل." },
  { term: "درجة الثقة", definition: "درجة غير معايرة من 0–100 (أعلى قيمة بين درجة النموذج ودرجة الدمج). ليست احتمالية وليست دقّة." },
  { term: "الخطورة", definition: "فئة الأولوية للقرار: حرج / مرتفع / متوسط. تُستخدم للفرز، ولا تُشتق من الدرجة." },
  { term: "نطاق الجلسة", definition: "الأرقام مشتقة من التنبيهات المستلمة في هذه الجلسة (حتى 50 تنبيهًا)، وليست سجلاً تاريخياً." },
]

/** Relative time is derived from one feed-wide clock, never a timer in each row. */
export function formatAlertRelativeArabic(isoTime: string, now: number): string {
  const then = Date.parse(isoTime)
  if (!Number.isFinite(then)) return "وقت غير متاح"
  const minutes = Math.max(0, Math.floor((now - then) / 60_000))
  if (minutes === 0) return "الآن"
  if (minutes === 1) return "قبل دقيقة"
  if (minutes === 2) return "قبل دقيقتين"
  if (minutes < 60) return `قبل ${minutes} دقيقة`
  const hours = Math.floor(minutes / 60)
  if (hours === 1) return "قبل ساعة"
  if (hours === 2) return "قبل ساعتين"
  if (hours < 24) return `قبل ${hours} ساعات`
  const days = Math.floor(hours / 24)
  return days === 1 ? "قبل يوم" : days === 2 ? "قبل يومين" : `قبل ${days} أيام`
}

export function minuteHeatBuckets(
  alerts: readonly { isoTime: string; severity: string }[],
  now: number,
  minuteCount = 30,
): { start: number; total: number; critical: number }[] {
  const count = Math.max(1, Math.min(120, Math.floor(minuteCount)))
  const start = now - count * 60_000
  const buckets = Array.from({ length: count }, (_, index) => ({
    start: start + index * 60_000, total: 0, critical: 0,
  }))
  for (const alert of alerts) {
    const time = Date.parse(alert.isoTime)
    const index = Math.floor((time - start) / 60_000)
    if (Number.isFinite(time) && index >= 0 && index < buckets.length) {
      buckets[index].total++
      if (alert.severity === "critical") buckets[index].critical++
    }
  }
  return buckets
}

export const CATEGORY_ICONS: Record<DetectionCategory, string> = {
  violence: "AlertTriangle",
  weapon: "Crosshair",
  crowd_surge: "Users",
  fall: "ArrowDown",
  intrusion: "ShieldAlert",
  loitering: "Clock",
}

export interface ThreatBox {
  id: string
  type: "violence" | "weapon"
  weaponType?: "gun" | "knife" | "explosive" | "unknown"
  bbox: [number, number, number, number]
  confidence: number
  color: [number, number, number]
  label: string
}

export interface MultiThreatData {
  hasViolence: boolean
  hasWeapon: boolean
  isMultiThreat: boolean
  violenceScore: number
  weaponScore: number
  fusedScore: number
  severity: "low" | "medium" | "high" | "critical"
  threatBoxes: ThreatBox[]
  reason: string
}

/* ---------------------------------------------------------------------------
 * Person tracking / counting contracts (S-04 / WT-22, additive to SC-2/SC-3)
 *
 * Multi-camera NON-association is structural here: a track reference embeds the
 * camera namespace (`"<cameraId>::<trackId>"`), so a reference from one camera
 * can never equal a reference from another, and the helpers below refuse to
 * compare identities across cameras. The runtime never associates tracks across
 * cameras, and these types make an accidental association a type error.
 * ------------------------------------------------------------------------- */

export type TrackRef = `${string}::${number}`

export interface CameraTrack {
  /** Human-facing label ("Person 3"). */
  id: string
  /** Camera-scoped identity — never compare across cameras. */
  ref: TrackRef
  bbox: [number, number, number, number]
  confidence: number
  label?: string
}

export interface CameraScopedTracks {
  cameraId: string
  tracks: CameraTrack[]
}

export function makeTrackRef(cameraId: string, trackId: number): TrackRef {
  const camera = cameraId.trim()
  if (!camera) throw new Error("trackRef requires a camera namespace")
  if (!Number.isSafeInteger(trackId) || trackId < 0) throw new Error("trackId must be a non-negative integer")
  return `${camera}::${trackId}`
}

export function parseTrackRef(ref: string): { cameraId: string; trackId: number } | null {
  const index = ref.indexOf("::")
  if (index <= 0) return null
  const cameraId = ref.slice(0, index)
  const raw = ref.slice(index + 2)
  if (!/^\d+$/.test(raw)) return null
  return { cameraId, trackId: Number(raw) }
}

/**
 * Cross-camera association is impossible by design. Comparing two identities
 * from different cameras is a programming error, not a runtime condition.
 */
export function assertSameTrackNamespace(a: TrackRef, b: TrackRef): void {
  const left = parseTrackRef(a)
  const right = parseTrackRef(b)
  if (left === null || right === null) throw new Error("malformed trackRef")
  if (left.cameraId !== right.cameraId) {
    throw new Error(`refusing to associate tracks across cameras: ${left.cameraId} vs ${right.cameraId}`)
  }
}

/** Uncertainty band is a >= / ± style interval derived from suspicion events. */
export interface UniquePersonEstimateWindow {
  windowSeconds: number
  uniqueTrackIds: number
  estimate: number
  bandLabel: string
  bandAbs: number
  estimateLower: number
  estimateUpper: number
  /** Never true today: the band is suspicion-derived, not calibrated. */
  bandIsCalibrated: false
}

export interface TrackFailureFlags {
  idSwitch: number
  reEntry: number
  mergeSplit: number
  dropout: number
  drift: number
}

export interface PersonCountingSnapshot {
  /** Detections in the current processed frame. */
  visiblePersonCount: number
  /** Confirmed tracks in the current processed frame. */
  activeTrackCount: number
  /** Documented alias of activeTrackCount (legacy field name). */
  personCount: number
  uniquePersonEstimateWindow: UniquePersonEstimateWindow | null
  trackFailureFlags: TrackFailureFlags
  personTracker: string
  trackNamespace: string
}

export interface PersonDetectionEvent extends PersonCountingSnapshot {
  type: "person_detection"
  cameraId: string
  trackIds: string[]
  isThreat: boolean
  videoWidth: number
  videoHeight: number
}

/** Incident capture state surfaced to the incident view (contract for WT-25). */
export type CaptureState = "pending" | "idle" | "ready" | "failed" | "dropped"

export interface IncidentCaptureStatus {
  state: CaptureState
  alertId?: string
  preCandidates?: number
  pending?: number
  droppedFrames?: number
}

function optionalCount(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null
}

function optionalFlags(value: unknown): TrackFailureFlags {
  const keys = ["idSwitch", "reEntry", "mergeSplit", "dropout", "drift"] as const
  const source = (value ?? {}) as Record<string, unknown>
  const flags = {} as TrackFailureFlags
  for (const key of keys) {
    const parsed = optionalCount(source[key])
    flags[key] = parsed ?? 0
  }
  return flags
}

function optionalWindow(value: unknown, fallbackWindowSeconds: number): UniquePersonEstimateWindow | null {
  if (typeof value !== "object" || value === null) return null
  const source = value as Record<string, unknown>
  const estimate = optionalCount(source.estimate)
  const uniqueTrackIds = optionalCount(source.uniqueTrackIds)
  if (estimate === null || uniqueTrackIds === null) return null
  const bandAbs = optionalCount(source.bandAbs) ?? 0
  return {
    windowSeconds: typeof source.windowSeconds === "number" ? source.windowSeconds : fallbackWindowSeconds,
    uniqueTrackIds,
    estimate,
    bandLabel: typeof source.bandLabel === "string" ? source.bandLabel : `±${bandAbs}`,
    bandAbs,
    estimateLower: optionalCount(source.estimateLower) ?? Math.max(0, estimate - bandAbs),
    estimateUpper: optionalCount(source.estimateUpper) ?? estimate + bandAbs,
    bandIsCalibrated: false,
  }
}

/**
 * Parse a `person_detection` SSE event. Returns null for anything malformed or
 * from a different camera; missing values stay unavailable rather than zero.
 */
export function parsePersonDetectionEvent(
  value: unknown,
  cameraId: string,
  fallbackWindowSeconds = 60,
): PersonDetectionEvent | null {
  if (typeof value !== "object" || value === null) return null
  const source = value as Record<string, unknown>
  if (source.type !== "person_detection") return null
  if (typeof source.cameraId !== "string" || source.cameraId !== cameraId) return null
  const rawPersonCount = optionalCount(source.personCount)
  const activeTrackCount = optionalCount(source.activeTrackCount) ?? rawPersonCount
  if (activeTrackCount === null) return null
  // `personCount` is the documented legacy alias of `activeTrackCount`; fall
  // back to it when the wire value is absent so the field is always a number.
  const personCount = rawPersonCount ?? activeTrackCount
  if (typeof source.isThreat !== "boolean") return null
  return {
    type: "person_detection",
    cameraId: source.cameraId,
    personCount,
    activeTrackCount,
    visiblePersonCount: optionalCount(source.visiblePersonCount) ?? activeTrackCount,
    uniquePersonEstimateWindow: optionalWindow(source.uniquePersonEstimateWindow, fallbackWindowSeconds),
    trackFailureFlags: optionalFlags(source.trackFailureFlags),
    personTracker: typeof source.personTracker === "string" ? source.personTracker : "",
    trackNamespace: typeof source.trackNamespace === "string" ? source.trackNamespace : source.cameraId,
    trackIds: Array.isArray(source.trackIds) ? source.trackIds.filter((item): item is string => typeof item === "string") : [],
    isThreat: source.isThreat,
    videoWidth: optionalCount(source.videoWidth) ?? 0,
    videoHeight: optionalCount(source.videoHeight) ?? 0,
  }
}
