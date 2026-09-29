import assert from "node:assert/strict"
import test from "node:test"
import { parseDetectionOverlayEnvelope } from "../lib/detection-envelope.ts"

const valid = {
  tracks: [{ id: "P-01", bbox: [10, 20, 110, 220], confidence: 0.92, color: [0, 255, 255] }],
  personCount: 1,
  isThreat: true,
  threatConfidence: 87,
  fps: 24,
  weaponScore: 41,
  videoWidth: 1280,
  videoHeight: 720,
}

test("detection stream accepts a valid overlay envelope", () => {
  assert.equal(parseDetectionOverlayEnvelope(valid)?.tracks[0].id, "P-01")
})

test("detection stream rejects hostile track labels before canvas rendering", () => {
  const payload = structuredClone(valid)
  payload.tracks[0].id = { toString: "not callable" }
  assert.equal(parseDetectionOverlayEnvelope(payload), null)
})

test("detection stream rejects malformed geometry and percentages", () => {
  for (const patch of [
    { tracks: [{ ...valid.tracks[0], bbox: [0, 0, "bad", 1] }] },
    { tracks: [{ ...valid.tracks[0], confidence: 1.5 }] },
    { threatConfidence: 101 },
    { personCount: -1 },
  ]) {
    assert.equal(parseDetectionOverlayEnvelope({ ...valid, ...patch }), null)
  }
})
