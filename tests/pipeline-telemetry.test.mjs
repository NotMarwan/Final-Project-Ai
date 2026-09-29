import test from "node:test"
import assert from "node:assert/strict"
import { applyModalityFreshness, emptyModalityFreshness, parseTelemetry, appendTelemetryPoint, telemetryIsStale, inferenceIsStale, updateModalityFreshness, frameAgeAtDisplayMs } from "../lib/pipeline-telemetry.ts"

const snapshot = (overrides = {}) => parseTelemetry({cameraId: "CAM-01", inferenceSequence: 1, violenceSequence: 1, weaponSequence: 1, sourceKind: "file", violenceScore: 0.3, weaponScore: 0.1, ...overrides}, "CAM-01")

test("missing data cannot imply NORMAL or zero scores", () => {
  const result = parseTelemetry({}, "CAM-01")
  assert.equal(result.decisionState, null)
  assert.equal(result.violenceScore, null)
  assert.equal(result.weaponScore, null)
  assert.equal(result.sourceKind, null)
  assert.equal(result.confirmThreshold, null)
})

test("camera IDs and explicit decision state define the boundary", () => {
  assert.equal(parseTelemetry({cameraId: "CAM-02"}, "CAM-01"), null)
  assert.equal(snapshot({violenceScore: 1, isThreat: true}).decisionState, null)
  assert.equal(snapshot({decision: {alertState: "CONFIRMED_VIOLENCE"}}).decisionState, "CONFIRMED")
  assert.equal(snapshot({decision: {alertState: "COOLDOWN", confirmedAlert: true}}).decisionState, "COOLDOWN")
})

test("out-of-range and malformed values remain unavailable", () => {
  const result = snapshot({violenceScore: 88, weaponScore: "0.9", decision: {confirmThreshold: -1}, window: {framesRequired: -4}, latencyMs: NaN})
  assert.equal(result.violenceScore, null)
  assert.equal(result.weaponScore, null)
  assert.equal(result.confirmThreshold, null)
  assert.equal(result.framesRequired, null)
  assert.equal(result.latencyMs, null)
})

test("confirmed event boolean never promotes an unknown state", () => {
  assert.equal(snapshot({decision: {confirmedAlert: true, alertState: "PENDING"}}).decisionState, null)
})

test("trace appends completed observations once despite repeated renders", () => {
  assert.deepEqual(appendTelemetryPoint([], snapshot({inferenceSequence: 0}), 1000), [])
  const first = appendTelemetryPoint([], snapshot(), 1000)
  assert.equal(first.length, 1)
  assert.equal(appendTelemetryPoint(first, snapshot({violenceScore: 0.9}), 1100), first)
  assert.equal(appendTelemetryPoint(first, snapshot({inferenceSequence: undefined}), 1200), first)
  const second = appendTelemetryPoint(first, snapshot({inferenceSequence: 2}), 2000)
  assert.equal(second.length, 2)
  assert.equal(second[0].violence, 0.3)
})

test("restarted pipelines reset trace and old observations expire", () => {
  const first = appendTelemetryPoint([], snapshot({inferenceSequence: 9}), 1000)
  const restarted = appendTelemetryPoint(first, snapshot({inferenceSequence: 1}), 2000)
  assert.equal(restarted.length, 1)
  const later = appendTelemetryPoint(restarted, snapshot({inferenceSequence: 2}), 63000)
  assert.equal(later.length, 1)
})

test("stale server samples cannot look fresh after reconnect", () => {
  const result = snapshot({updatedAt: 1})
  assert.equal(telemetryIsStale(result, 9000, 9000), true)
  assert.equal(telemetryIsStale(snapshot({updatedAt: 9}), 9000, 10000), false)
  assert.equal(telemetryIsStale(snapshot(), 1000, 7000), true)
  assert.equal(telemetryIsStale(null, null, 0), true)
})

test("subsystem health is explicit and preserves disabled/failed distinctions", () => {
  const result = snapshot({health: {person: {status: "DISABLED", reason: "Not configured"}, weapon: {status: "FAILED", reason: "Model missing"}}})
  assert.equal(result.health.person.status, "DISABLED")
  assert.equal(result.health.weapon.status, "FAILED")
  assert.equal(result.health.violence, undefined)
})


test("fresh render traffic cannot revive a stalled inference", () => {
  assert.equal(inferenceIsStale(12, 1000, 7000), true)
  assert.equal(inferenceIsStale(13, 7000, 7000), false)
  assert.equal(inferenceIsStale(0, null, 7000), true)
})


test("weapon-only completions do not fabricate violence observations", () => {
  const first = appendTelemetryPoint([], snapshot(), 1000)
  const weaponOnly = appendTelemetryPoint(first, snapshot({inferenceSequence: 2, weaponSequence: 2}), 1200)
  assert.equal(weaponOnly[1].violence, null)
  assert.equal(weaponOnly[1].weapon, 0.1)
  const violenceOnly = appendTelemetryPoint(weaponOnly, snapshot({inferenceSequence: 3, violenceSequence: 2, weaponSequence: 2}), 1400)
  assert.equal(violenceOnly[2].violence, 0.3)
  assert.equal(violenceOnly[2].weapon, null)
})

test("weapon completions cannot keep a stalled violence modality fresh", () => {
  const first = snapshot({health: {violence: {status: "OK"}, weapon: {status: "OK"}}})
  let freshness = updateModalityFreshness(emptyModalityFreshness(), first, 1000)
  const weaponContinues = snapshot({inferenceSequence: 3, violenceSequence: 1, weaponSequence: 3, violenceScore: 0.8, weaponScore: 0.2, health: {violence: {status: "OK"}, weapon: {status: "OK"}}})
  freshness = updateModalityFreshness(freshness, weaponContinues, 7001)

  const result = applyModalityFreshness(weaponContinues, freshness, 7001)
  assert.equal(result.violenceScore, null)
  assert.equal(result.weaponScore, 0.2)
  assert.equal(result.health.violence.status, "DEGRADED")
  assert.equal(result.health.weapon.status, "OK")
})

test("violence completions cannot keep a stalled weapon modality fresh", () => {
  const first = snapshot({health: {violence: {status: "OK"}, weapon: {status: "OK"}}})
  let freshness = updateModalityFreshness(emptyModalityFreshness(), first, 1000)
  const violenceContinues = snapshot({inferenceSequence: 3, violenceSequence: 3, weaponSequence: 1, violenceScore: 0.6, weaponScore: 0.7, health: {violence: {status: "OK"}, weapon: {status: "OK"}}})
  freshness = updateModalityFreshness(freshness, violenceContinues, 7001)

  const result = applyModalityFreshness(violenceContinues, freshness, 7001)
  assert.equal(result.violenceScore, 0.6)
  assert.equal(result.weaponScore, null)
  assert.equal(result.health.violence.status, "OK")
  assert.equal(result.health.weapon.status, "DEGRADED")
})

test("a combined sequence without producer IDs cannot invent model samples", () => {
  const result = appendTelemetryPoint([], snapshot({violenceSequence: undefined, weaponSequence: undefined}), 1000)
  assert.equal(result[0].violence, null)
  assert.equal(result[0].weapon, null)
})


test("top-level calibration and window clocks preserve backend meaning", () => {
  const result = snapshot({calibrationStatus: "unverified", window: {clockSource: "file-media", spanSeconds: 1.2}})
  assert.equal(result.calibrationStatus, "unverified")
  assert.equal(result.windowClockSource, "file-media")
  assert.equal(result.windowSpanSeconds, 1.2)
})

const metricsBlock = (overrides = {}) => ({
  available: true,
  schemaVersion: "sentinel-metrics-export/1",
  frameAgeMs: {atInferenceStart: 41.5, atPublication: 52.25, clockSource: "monotonic-capture"},
  stageMs: {frameRead: 6.25, captureToQueue: 3.5, preprocess: 4, enqueueToDequeue: 12.5, inferenceWait: 8, inferenceCompute: 24, modelLoad: 1450},
  queues: {frameDepth: 1, frameQueueDropped: 3, frameQueueDroppedDerived: 3, resultDepth: 2, resultQueueDropped: 0, backlogFrames: 0},
  counters: {personCompletedCount: 120, violenceCompletedCount: 40, weaponCompletedCount: 10, framesReadCount: 900, duplicateFrameCount: 2, reconnectCount: 0, processRunId: "run-A", inferenceGeneration: 2},
  inferenceComputeSynced: true,
  processingLatencyMs: 87.5,
  unavailable: ["queues.resultQueueDropped"],
  ...overrides,
})

test("stage, queue and frame-age telemetry parse with explicit clock labels", () => {
  const result = snapshot({pipeline: metricsBlock()})
  assert.equal(result.pipeline.schemaVersion, "sentinel-metrics-export/1")
  assert.equal(result.pipeline.frameAgeMs.atInferenceStart, 41.5)
  assert.equal(result.pipeline.frameAgeMs.atPublication, 52.25)
  assert.equal(result.pipeline.frameAgeMs.clockSource, "monotonic-capture")
  assert.equal(result.pipeline.stageMs.enqueueToDequeue, 12.5)
  assert.equal(result.pipeline.stageMs.inferenceCompute, 24)
  assert.equal(result.pipeline.stageMs.modelLoad, 1450)
  assert.equal(result.pipeline.queues.frameQueueDropped, 3)
  assert.equal(result.pipeline.queues.frameQueueDroppedDerived, 3)
  assert.equal(result.pipeline.queues.backlogFrames, 0)
  assert.equal(result.pipeline.counters.personCompletedCount, 120)
  assert.equal(result.pipeline.counters.framesReadCount, 900)
  assert.equal(result.pipeline.processRunId, "run-A")
  assert.equal(result.pipeline.inferenceGeneration, 2)
  assert.equal(result.pipeline.inferenceComputeSynced, true)
  assert.equal(result.pipeline.processingLatencyMs, 87.5)
  assert.deepEqual(result.pipeline.unavailable, ["queues.resultQueueDropped"])
})

test("absent, unavailable and malformed telemetry stays unavailable instead of zero", () => {
  assert.equal(parseTelemetry({cameraId: "CAM-01"}, "CAM-01").pipeline, null)
  assert.equal(snapshot({pipeline: {available: false, reason: "telemetry unavailable"}}).pipeline, null)
  const malformed = snapshot({pipeline: {
    available: true,
    schemaVersion: 42,
    frameAgeMs: {atInferenceStart: -3, atPublication: "fast", clockSource: 9},
    stageMs: {preprocess: -1, inferenceCompute: NaN, frameRead: "6"},
    queues: {frameDepth: -2, frameQueueDropped: "3", backlogFrames: null},
    counters: {personCompletedCount: -7, violenceCompletedCount: 0, processRunId: 5, inferenceGeneration: -1},
    inferenceComputeSynced: "yes",
    processingLatencyMs: -10,
    unavailable: ["stageMs.frameRead", 7, {path: "x"}],
  }})
  assert.equal(malformed.pipeline.schemaVersion, null)
  assert.equal(malformed.pipeline.frameAgeMs.atInferenceStart, null)
  assert.equal(malformed.pipeline.frameAgeMs.atPublication, null)
  assert.equal(malformed.pipeline.frameAgeMs.clockSource, null)
  assert.equal(malformed.pipeline.stageMs.preprocess, null)
  assert.equal(malformed.pipeline.stageMs.inferenceCompute, null)
  assert.equal(malformed.pipeline.stageMs.frameRead, null)
  assert.equal(malformed.pipeline.queues.frameDepth, null)
  assert.equal(malformed.pipeline.queues.frameQueueDropped, null)
  assert.equal(malformed.pipeline.queues.backlogFrames, null)
  assert.equal(malformed.pipeline.counters.personCompletedCount, null)
  assert.equal(malformed.pipeline.counters.violenceCompletedCount, 0)
  assert.equal(malformed.pipeline.processRunId, null)
  assert.equal(malformed.pipeline.inferenceGeneration, null)
  assert.equal(malformed.pipeline.inferenceComputeSynced, null)
  assert.equal(malformed.pipeline.processingLatencyMs, null)
  assert.deepEqual(malformed.pipeline.unavailable, ["stageMs.frameRead"])
})

test("frame age at display needs both clocks and never goes negative", () => {
  assert.equal(frameAgeAtDisplayMs(null, 100_000), null)
  assert.equal(frameAgeAtDisplayMs(0, 100_000), null)
  assert.equal(frameAgeAtDisplayMs(Number.NaN, 100_000), null)
  assert.equal(frameAgeAtDisplayMs(100_000, Number.NaN), null)
  assert.equal(frameAgeAtDisplayMs(101_000, 100_000), null)
  assert.equal(frameAgeAtDisplayMs(100_000, 100_000), 0)
  assert.equal(frameAgeAtDisplayMs(97_500, 100_000), 2_500)
})

test("modality freshness degradation keeps the pipeline telemetry block", () => {
  const withHealth = snapshot({health: {violence: {status: "OK"}, weapon: {status: "OK"}}, pipeline: metricsBlock()})
  let freshness = updateModalityFreshness(emptyModalityFreshness(), withHealth, 1000)
  const stale = snapshot({inferenceSequence: 3, violenceSequence: 1, weaponSequence: 3, health: {violence: {status: "OK"}, weapon: {status: "OK"}}, pipeline: metricsBlock()})
  freshness = updateModalityFreshness(freshness, stale, 7001)
  const result = applyModalityFreshness(stale, freshness, 7001)
  assert.equal(result.violenceScore, null)
  assert.equal(result.pipeline.stageMs.inferenceCompute, 24)
  assert.equal(result.pipeline.counters.violenceCompletedCount, 40)
})

test("display frame telemetry parses additively and never invents values", () => {
  const measured = snapshot({
    frameSequence: 812,
    frameAgeAtDetectionEmitMs: 71.5,
    frameAgeAtDetectionEmitClockBase: "monotonic-gettickcount64",
    renderBacklogDroppedCount: 4,
  })
  assert.equal(measured.displayFrameSequence, 812)
  assert.equal(measured.displayFrameAgeMs, 71.5)
  assert.equal(measured.displayFrameAgeClockBase, "monotonic-gettickcount64")
  assert.equal(measured.renderBacklogDroppedCount, 4)

  const absent = snapshot()
  assert.equal(absent.displayFrameSequence, null)
  assert.equal(absent.displayFrameAgeMs, null)
  assert.equal(absent.displayFrameAgeClockBase, null)
  assert.equal(absent.renderBacklogDroppedCount, null)

  const malformed = snapshot({
    frameSequence: -3,
    frameAgeAtDetectionEmitMs: "fast",
    frameAgeAtDetectionEmitClockBase: 7,
    renderBacklogDroppedCount: -1,
  })
  assert.equal(malformed.displayFrameSequence, null)
  assert.equal(malformed.displayFrameAgeMs, null)
  assert.equal(malformed.displayFrameAgeClockBase, null)
  assert.equal(malformed.renderBacklogDroppedCount, null)
})
