import assert from "node:assert/strict"
import test from "node:test"
import { isOverlayFrameCorrelated, parseDetectionOverlayEnvelope } from "../lib/detection-envelope.ts"
import { sourceVisualState } from "../lib/live-visual-state.ts"

const baseEnvelope = {
  tracks: [],
  personCount: 1,
  isThreat: false,
  threatConfidence: 12,
  fps: 24,
  videoWidth: 1280,
  videoHeight: 720,
}

test("overlay envelope carries frameSequence when present and omits it when absent", () => {
  const withIdentity = parseDetectionOverlayEnvelope({ ...baseEnvelope, frameSequence: 42 })
  assert.equal(withIdentity?.frameSequence, 42)

  const withoutIdentity = parseDetectionOverlayEnvelope({ ...baseEnvelope })
  assert.ok(withoutIdentity)
  assert.equal("frameSequence" in withoutIdentity, false)

  const explicitNull = parseDetectionOverlayEnvelope({ ...baseEnvelope, frameSequence: null })
  assert.ok(explicitNull)
  assert.equal("frameSequence" in explicitNull, false)
})

test("malformed frameSequence fails the envelope closed", () => {
  for (const frameSequence of [-1, 1.5, "42", Number.MAX_SAFE_INTEGER + 1, Number.NaN, {}]) {
    assert.equal(parseDetectionOverlayEnvelope({ ...baseEnvelope, frameSequence }), null, String(frameSequence))
  }
})

test("client overlay draws only when the payload frame is proven identical to the display frame", () => {
  assert.equal(isOverlayFrameCorrelated(7, 7), true)
  // A decision that arrives late must not paint its labels on a different frame.
  assert.equal(isOverlayFrameCorrelated(7, 8), false)
  assert.equal(isOverlayFrameCorrelated(8, 7), false)
  // Correlation absent (plain <img> MJPEG) or malformed: overlay hides itself.
  assert.equal(isOverlayFrameCorrelated(7, null), false)
  assert.equal(isOverlayFrameCorrelated(7, undefined), false)
  assert.equal(isOverlayFrameCorrelated(null, 7), false)
  assert.equal(isOverlayFrameCorrelated(undefined, undefined), false)
  assert.equal(isOverlayFrameCorrelated(0, 0), false)
  assert.equal(isOverlayFrameCorrelated(2.5, 2.5), false)
})

test("a file source is never labelled live and a stale stream raises the stale banner", () => {
  const base = {
    connected: true, stale: false, inferenceStale: false, frameReady: true,
    failed: false, sourceKind: "file", isDemo: false, externalPlayback: false,
  }
  assert.equal(sourceVisualState(base), "replay")
  assert.equal(sourceVisualState({ ...base, sourceKind: null, isDemo: true }), "replay")
  assert.equal(sourceVisualState({ ...base, sourceKind: "live" }), "live")

  // 5s telemetry staleness (>5_000 ms handled by telemetryIsStale upstream) plus a
  // stalled stream both route to the stale banner rather than a false live badge.
  assert.equal(sourceVisualState({ ...base, stale: true, sourceKind: "live" }), "stale")
  assert.equal(sourceVisualState({ ...base, inferenceStale: true, sourceKind: "live" }), "stale")
})
