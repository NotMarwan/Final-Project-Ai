import test from "node:test"
import assert from "node:assert/strict"
import {
  assertSameTrackNamespace,
  makeTrackRef,
  parsePersonDetectionEvent,
  parseTrackRef,
} from "../lib/detection-types.ts"

test("track references are camera-scoped and cannot collide across cameras", () => {
  const a = makeTrackRef("CAM-01", 7)
  const b = makeTrackRef("CAM-02", 7)
  assert.equal(a, "CAM-01::7")
  assert.notEqual(a, b)
  assert.deepEqual(parseTrackRef(a), { cameraId: "CAM-01", trackId: 7 })
  assert.equal(parseTrackRef("CAM-01:7"), null)
  assert.equal(parseTrackRef("bare"), null)
  assert.throws(() => makeTrackRef("  ", 1), /camera namespace/)
})

test("cross-camera association is refused, same-camera association is allowed", () => {
  assert.doesNotThrow(() => assertSameTrackNamespace(makeTrackRef("CAM-01", 1), makeTrackRef("CAM-01", 2)))
  assert.throws(() => assertSameTrackNamespace(makeTrackRef("CAM-01", 1), makeTrackRef("CAM-02", 1)),
    /refusing to associate tracks across cameras/)
})

test("person_detection events from another camera or malformed payloads are rejected", () => {
  assert.equal(parsePersonDetectionEvent({type: "person_detection", cameraId: "CAM-02", personCount: 1, isThreat: false}, "CAM-01"), null)
  assert.equal(parsePersonDetectionEvent({type: "alert", cameraId: "CAM-01", personCount: 1, isThreat: false}, "CAM-01"), null)
  assert.equal(parsePersonDetectionEvent(null, "CAM-01"), null)
  assert.equal(parsePersonDetectionEvent({type: "person_detection", cameraId: "CAM-01", isThreat: false}, "CAM-01"), null)
})

test("counting fields parse additively and missing values never become zero-free claims", () => {
  const parsed = parsePersonDetectionEvent({
    type: "person_detection",
    cameraId: "CAM-01",
    personCount: 2,
    activeTrackCount: 2,
    visiblePersonCount: 4,
    isThreat: true,
    trackIds: ["CAM-01::1", "CAM-01::2"],
    videoWidth: 1280,
    videoHeight: 720,
    personTracker: "bytetrack",
    trackFailureFlags: {idSwitch: 1, dropout: 2, drift: "bad"},
    uniquePersonEstimateWindow: {
      windowSeconds: 60,
      uniqueTrackIds: 5,
      estimate: 5,
      bandLabel: "±3",
      bandAbs: 3,
      estimateLower: 2,
      estimateUpper: 8,
    },
  }, "CAM-01")
  assert.ok(parsed)
  assert.equal(parsed.activeTrackCount, 2)
  assert.equal(parsed.visiblePersonCount, 4)
  assert.equal(parsed.personCount, 2)
  assert.equal(parsed.trackNamespace, "CAM-01")
  assert.deepEqual(parsed.trackFailureFlags, {idSwitch: 1, reEntry: 0, mergeSplit: 0, dropout: 2, drift: 0})
  assert.equal(parsed.uniquePersonEstimateWindow?.bandLabel, "±3")
  assert.equal(parsed.uniquePersonEstimateWindow?.bandIsCalibrated, false)

  const legacy = parsePersonDetectionEvent({type: "person_detection", cameraId: "CAM-01", personCount: 3, isThreat: false}, "CAM-01")
  assert.ok(legacy)
  assert.equal(legacy.uniquePersonEstimateWindow, null)
  assert.equal(legacy.activeTrackCount, 3)
  assert.equal(legacy.visiblePersonCount, 3)
  assert.equal(legacy.personTracker, "")
})
