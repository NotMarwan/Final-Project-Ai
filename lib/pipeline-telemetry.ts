export type DecisionState = "NORMAL" | "WATCH" | "CONFIRMED" | "COOLDOWN"
export type TelemetryHealth = { status: string; reason: string }
export type PipelineTelemetry = {
  cameraId: string
  sourceKind: "live" | "file" | null
  updatedAt: number | null
  sequence: number | null
  violenceSequence: number | null
  weaponSequence: number | null
  violenceScore: number | null
  weaponScore: number | null
  decisionState: DecisionState | null
  confirmThreshold: number | null
  watchThreshold: number | null
  weaponThreshold: number | null
  confirmN: number | null
  confirmM: number | null
  rollingWindowCount: number | null
  cooldownRemainingSeconds: number | null
  framesCollected: number | null
  framesRequired: number | null
  windowSpanSeconds: number | null
  windowValid: boolean | null
  windowClockSource: "file-media" | "monotonic-capture" | null
  latencyMs: number | null
  calibrationStatus: string | null
  health: Record<string, TelemetryHealth>
  pipeline: PipelineMetricsBlock | null
  displayFrameSequence: number | null
  displayFrameAgeMs: number | null
  displayFrameAgeClockBase: string | null
  renderBacklogDroppedCount: number | null
}
export type TelemetryPoint = { sequence: number; time: number; violence: number | null; weapon: number | null; violenceSequence: number | null; weaponSequence: number | null }
export type ModalityFreshness = {
  violenceSequence: number | null
  weaponSequence: number | null
  violenceReceivedAt: number | null
  weaponReceivedAt: number | null
}

/** Distribution summary emitted by backend/metrics.py (`pipeline` block on /detections). */
export type MetricDistribution = {
  p05: number | null
  median: number | null
  p95: number | null
  min: number | null
  max: number | null
  n: number
  unit: string
}

/**
 * Per-frame telemetry attached additively to the /detections payload (WT-13, S-08).
 * Every value is `null` when unmeasured; a null is never rendered as zero.
 */
export type PipelineMetricsBlock = {
  schemaVersion: string | null
  stageMs: Record<string, number | null>
  frameAgeMs: {
    atInferenceStart: number | null
    atPublication: number | null
    clockSource: string | null
  }
  queues: Record<string, number | null>
  counters: Record<string, number | null>
  processRunId: string | null
  inferenceGeneration: number | null
  inferenceComputeSynced: boolean | null
  processingLatencyMs: number | null
  unavailable: string[]
}

export const PIPELINE_STAGE_NAMES = [
  "frameRead", "captureToQueue", "preprocess", "serialize", "enqueueToDequeue",
  "inferenceWait", "inferenceCompute", "modelLoad", "firstInference", "engineBuild", "inferenceColdStart",
] as const
export const PIPELINE_QUEUE_NAMES = [
  "frameDepth", "frameQueueDropped", "frameQueueDroppedDerived", "resultDepth", "resultQueueDropped", "backlogFrames",
] as const
export const PIPELINE_COUNTER_NAMES = [
  "personCompletedCount", "violenceCompletedCount", "weaponCompletedCount",
  "framesReadCount", "duplicateFrameCount", "reconnectCount",
] as const

/**
 * Frame age at display: browser wall-clock minus the backend wall-clock publication
 * stamp. This is a wall-epoch difference across two clocks (browser vs server), NOT a
 * monotonic measurement and NOT glass-to-alert; it is labelled as such in the UI.
 */
export const FRAME_AGE_AT_DISPLAY_CLOCK = "wall-epoch (browser) - wall-epoch (backend); cross-clock estimate"

export function frameAgeAtDisplayMs(updatedAtEpochMs: number | null, nowEpochMs: number): number | null {
  if (updatedAtEpochMs === null || !Number.isFinite(updatedAtEpochMs) || updatedAtEpochMs <= 0) return null
  if (!Number.isFinite(nowEpochMs)) return null
  const age = nowEpochMs - updatedAtEpochMs
  return age >= 0 ? age : null
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {}
}

export function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function nonNegative(value: unknown): number | null {
  const number = finiteNumber(value)
  return number !== null && number >= 0 ? number : null
}

function probability(value: unknown): number | null {
  const number = finiteNumber(value)
  return number !== null && number >= 0 && number <= 1 ? number : null
}

function nonNegativeInt(value: unknown): number | null {
  const number = nonNegative(value)
  return number === null ? null : Math.trunc(number)
}

function shortText(value: unknown, limit = 120): string | null {
  return typeof value === "string" && value.length > 0 ? value.slice(0, limit) : null
}

/**
 * Parse the additive `pipeline` telemetry block. Returns null when the backend did not
 * attach it (or explicitly marked it unavailable); individual fields stay null when
 * unmeasured so the UI can render "unavailable" instead of a fabricated zero.
 */
export function parsePipelineMetrics(value: unknown): PipelineMetricsBlock | null {
  const block = asRecord(value)
  if (Object.keys(block).length === 0) return null
  if (block.available === false) return null
  const rawStages = asRecord(block.stageMs)
  const stages: Record<string, number | null> = Object.create(null)
  for (const name of PIPELINE_STAGE_NAMES) stages[name] = nonNegative(rawStages[name])
  const rawQueues = asRecord(block.queues)
  const queues: Record<string, number | null> = Object.create(null)
  for (const name of PIPELINE_QUEUE_NAMES) queues[name] = nonNegativeInt(rawQueues[name])
  const rawCounters = asRecord(block.counters)
  const counters: Record<string, number | null> = Object.create(null)
  for (const name of PIPELINE_COUNTER_NAMES) counters[name] = nonNegativeInt(rawCounters[name])
  const rawAge = asRecord(block.frameAgeMs)
  const unavailable = Array.isArray(block.unavailable)
    ? block.unavailable.filter((item): item is string => typeof item === "string").slice(0, 64).map((item) => item.slice(0, 120))
    : []
  return {
    schemaVersion: shortText(block.schemaVersion, 64),
    stageMs: stages,
    frameAgeMs: {
      atInferenceStart: nonNegative(rawAge.atInferenceStart),
      atPublication: nonNegative(rawAge.atPublication),
      clockSource: shortText(rawAge.clockSource, 64),
    },
    queues,
    counters,
    processRunId: shortText(rawCounters.processRunId, 64),
    inferenceGeneration: nonNegativeInt(rawCounters.inferenceGeneration),
    inferenceComputeSynced: typeof block.inferenceComputeSynced === "boolean" ? block.inferenceComputeSynced : null,
    processingLatencyMs: nonNegative(block.processingLatencyMs),
    unavailable,
  }
}

export function parseTelemetry(value: unknown, cameraId: string): PipelineTelemetry | null {
  const data = asRecord(value)
  if (data.cameraId !== undefined && data.cameraId !== cameraId) return null
  const decision = asRecord(data.decision ?? data.decision_layer)
  const window = asRecord(data.window)
  const rawHealth = asRecord(data.health ?? data.pipeline_health)
  const health: Record<string, TelemetryHealth> = Object.create(null)
  for (const key of ["capture", "violence", "weapon", "person", "decision", "render"]) {
    const item = asRecord(rawHealth[key])
    if (typeof item.status === "string") {
      health[key] = {
        status: item.status.toUpperCase(),
        reason: typeof item.reason === "string" ? item.reason.slice(0, 240) : "",
      }
    }
  }
  const rawState = decision.alertState ?? decision.alert_state
  const state = rawState === "CONFIRMED_VIOLENCE" ? "CONFIRMED" : rawState
  const decisionState = ["NORMAL", "WATCH", "CONFIRMED", "COOLDOWN"].includes(String(state))
    ? state as DecisionState : null
  const rawTimestamp = data.updatedAt
  const updatedAt = typeof rawTimestamp === "string"
    ? finiteNumber(Date.parse(rawTimestamp))
    : nonNegative(rawTimestamp) === null ? null : (rawTimestamp as number) * 1000
  return {
    cameraId,
    sourceKind: data.sourceKind === "live" || data.sourceKind === "file" ? data.sourceKind : null,
    updatedAt,
    sequence: nonNegative(data.inferenceSequence ?? data.inference_sequence),
    violenceSequence: nonNegative(data.violenceSequence ?? data.violence_observation_id),
    weaponSequence: nonNegative(data.weaponSequence ?? data.weapon_observation_id),
    violenceScore: probability(data.violenceScore),
    weaponScore: probability(data.weaponScore),
    decisionState,
    confirmThreshold: probability(decision.confirmThreshold ?? decision.confirm_threshold),
    watchThreshold: probability(decision.watchThreshold ?? decision.watch_threshold),
    weaponThreshold: probability(decision.weaponThreshold ?? decision.weapon_threshold),
    confirmN: nonNegative(decision.confirmN ?? decision.confirm_n),
    confirmM: nonNegative(decision.confirmM ?? decision.confirm_m),
    rollingWindowCount: nonNegative(decision.rollingWindowCount ?? decision.rolling_window_count),
    cooldownRemainingSeconds: nonNegative(decision.cooldownRemainingSeconds ?? decision.cooldown_remaining_seconds),
    framesCollected: nonNegative(window.framesCollected),
    framesRequired: nonNegative(window.framesRequired),
    windowSpanSeconds: nonNegative(window.spanSeconds ?? data.window_span_seconds),
    windowValid: typeof window.valid === "boolean" ? window.valid : null,
    windowClockSource: window.clockSource === "file-media" || window.clockSource === "monotonic-capture" ? window.clockSource : null,
    latencyMs: nonNegative(data.latencyMs),
    calibrationStatus: typeof (data.calibrationStatus ?? decision.calibrationStatus ?? decision.calibration_status) === "string"
      ? String(data.calibrationStatus ?? decision.calibrationStatus ?? decision.calibration_status) : null,
    health,
    pipeline: parsePipelineMetrics(data.pipeline),
    displayFrameSequence: nonNegativeInt(data.frameSequence),
    displayFrameAgeMs: nonNegative(data.frameAgeAtDetectionEmitMs),
    displayFrameAgeClockBase: shortText(data.frameAgeAtDetectionEmitClockBase, 64),
    renderBacklogDroppedCount: nonNegativeInt(data.renderBacklogDroppedCount),
  }
}

// Render updates can repeat the same inference: only completed observations enter a trace.
export function appendTelemetryPoint(history: TelemetryPoint[], snapshot: PipelineTelemetry, receivedAt: number): TelemetryPoint[] {
  if (snapshot.sequence === null || snapshot.sequence <= 0) return history
  const last = history.at(-1)
  if (last?.sequence === snapshot.sequence) return history
  const restarted = last && (snapshot.sequence < last.sequence
    || (snapshot.violenceSequence !== null && last.violenceSequence !== null && snapshot.violenceSequence < last.violenceSequence)
    || (snapshot.weaponSequence !== null && last.weaponSequence !== null && snapshot.weaponSequence < last.weaponSequence))
  const next = restarted ? [] : history
  const previous = next.at(-1)
  const freshViolence = snapshot.violenceSequence !== null && snapshot.violenceSequence > 0 && snapshot.violenceSequence !== previous?.violenceSequence
  const freshWeapon = snapshot.weaponSequence !== null && snapshot.weaponSequence > 0 && snapshot.weaponSequence !== previous?.weaponSequence
  const point = {
    sequence: snapshot.sequence, time: receivedAt,
    violence: freshViolence ? snapshot.violenceScore : null,
    weapon: freshWeapon ? snapshot.weaponScore : null,
    violenceSequence: snapshot.violenceSequence, weaponSequence: snapshot.weaponSequence,
  }
  return [...next, point].filter(item => receivedAt - item.time <= 60_000).slice(-120)
}

export function telemetryIsStale(snapshot: PipelineTelemetry | null, receivedAt: number | null, now: number): boolean {
  if (!snapshot || receivedAt === null) return true
  return now - receivedAt > 5_000 || (snapshot.updatedAt !== null && now - snapshot.updatedAt > 5_000)
}

export function inferenceIsStale(sequence: number | null, sampleReceivedAt: number | null, now: number): boolean {
  return sequence === null || sequence <= 0 || sampleReceivedAt === null || now - sampleReceivedAt > 5_000
}

export const emptyModalityFreshness = (): ModalityFreshness => ({
  violenceSequence: null,
  weaponSequence: null,
  violenceReceivedAt: null,
  weaponReceivedAt: null,
})

export function updateModalityFreshness(
  previous: ModalityFreshness,
  snapshot: PipelineTelemetry,
  receivedAt: number,
): ModalityFreshness {
  const violenceCompleted = snapshot.violenceSequence !== null
    && snapshot.violenceSequence > 0
    && snapshot.violenceSequence !== previous.violenceSequence
  const weaponCompleted = snapshot.weaponSequence !== null
    && snapshot.weaponSequence > 0
    && snapshot.weaponSequence !== previous.weaponSequence
  return {
    violenceSequence: snapshot.violenceSequence,
    weaponSequence: snapshot.weaponSequence,
    violenceReceivedAt: violenceCompleted ? receivedAt : previous.violenceReceivedAt,
    weaponReceivedAt: weaponCompleted ? receivedAt : previous.weaponReceivedAt,
  }
}

function staleHealth(health: TelemetryHealth | undefined, modality: "violence" | "weapon"): TelemetryHealth {
  if (health && health.status !== "OK" && health.status !== "HEALTHY") return health
  return { status: "DEGRADED", reason: `No new ${modality} completion received in the last 5 seconds` }
}

export function applyModalityFreshness(
  snapshot: PipelineTelemetry,
  freshness: ModalityFreshness,
  now: number,
): PipelineTelemetry {
  const violenceStale = inferenceIsStale(snapshot.violenceSequence, freshness.violenceReceivedAt, now)
  const weaponStale = inferenceIsStale(snapshot.weaponSequence, freshness.weaponReceivedAt, now)
  if (!violenceStale && !weaponStale) return snapshot
  return {
    ...snapshot,
    violenceScore: violenceStale ? null : snapshot.violenceScore,
    weaponScore: weaponStale ? null : snapshot.weaponScore,
    health: {
      ...snapshot.health,
      ...(violenceStale ? { violence: staleHealth(snapshot.health.violence, "violence") } : {}),
      ...(weaponStale ? { weapon: staleHealth(snapshot.health.weapon, "weapon") } : {}),
    },
  }
}
