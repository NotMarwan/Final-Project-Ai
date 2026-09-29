import assert from "node:assert/strict"
import { test } from "node:test"
import { latencyPercentiles, parseAlertEnvelope, parsePersonCountEnvelope, selectThreatLevel, selectVisibleAlerts, timeBuckets } from "../sentinel-selectors.ts"

const now = Date.parse("2026-09-26T12:00:00.000Z")
const makeAlert = (id, cameraId, severity, minutesAgo) => ({
  id, cameraId, severity, type: "Weapon", confidence: 80, location: "اختبار", timestamp: "12:00",
  isoTime: new Date(now - minutesAgo * 60_000).toISOString(),
})

test("camera and severity filters combine with AND", () => {
  const alerts = [makeAlert("a", "CAM-01", "critical", 2), makeAlert("b", "CAM-01", "high", 2), makeAlert("c", "CAM-02", "critical", 2)]
  assert.deepEqual(selectVisibleAlerts(alerts, { cameraId: "CAM-01", severity: "critical", range: "15m" }, now).map((alert) => alert.id), ["a"])
})

test("camera, type, severity, confidence, and range filters all combine", () => {
  const alerts = [
    { ...makeAlert("a", "CAM-01", "critical", 2), confidence: 100 },
    { ...makeAlert("b", "CAM-01", "critical", 2), confidence: 85, type: "Violence" },
    { ...makeAlert("c", "CAM-01", "high", 2), confidence: 90 },
    { ...makeAlert("d", "CAM-02", "critical", 2), confidence: 99 },
    { ...makeAlert("e", "CAM-01", "critical", 20), confidence: 100 },
  ]
  const visible = selectVisibleAlerts(alerts, {
    cameraId: "CAM-01", type: "Weapon", severity: "critical", confidenceBand: 4, range: "15m",
  }, now)
  assert.deepEqual(visible.map((alert) => alert.id), ["a"])
})

test("range includes its start and current time and both land in timeline buckets", () => {
  const alerts = [
    makeAlert("start", "CAM-01", "high", 15),
    { ...makeAlert("now", "CAM-01", "high", 0), isoTime: new Date(now).toISOString() },
  ]
  const filters = { range: "15m" }
  const visible = selectVisibleAlerts(alerts, filters, now)
  const buckets = timeBuckets(visible, filters, now)
  assert.equal(visible.length, 2)
  assert.equal(buckets.reduce((sum, bucket) => sum + bucket.Weapon + bucket.Violence, 0), 2)
})

test("latency percentiles stay unavailable with fewer than two measured samples", () => {
  assert.deepEqual(latencyPercentiles([]), { p50: null, p95: null })
  assert.equal(latencyPercentiles([makeAlert("a", "CAM-01", "high", 1)]).p95, null)
  assert.deepEqual(latencyPercentiles([{ ...makeAlert("a", "CAM-01", "high", 1), alertLatencyMs: 230 }]), { p50: null, p95: null })
})

test("old critical alert does not set current threat level", () => {
  assert.equal(selectThreatLevel([makeAlert("a", "CAM-01", "critical", 20)], now), "calm")
})

test("backend weapon label enters the normalized alert feed", () => {
  assert.equal(parseAlertEnvelope({ ...makeAlert("a", "CAM-01", "high", 1), type: "Weapon Detection" })?.type, "Weapon")
})

test("alert envelopes reject invalid IDs, timestamps, and out-of-range confidence", () => {
  const valid = makeAlert("a", "CAM-01", "high", 1)
  for (const patch of [
    { id: "../secret" },
    { isoTime: "not-a-timestamp" },
    { confidence: -0.1 },
    { confidence: 100.1 },
  ]) {
    assert.equal(parseAlertEnvelope({ ...valid, ...patch }), null)
  }
})

test("alert envelopes omit unchecked optional fields instead of copying payload objects", () => {
  const parsed = parseAlertEnvelope({
    ...makeAlert("a", "CAM-01", "high", 1),
    weaponLabels: "not an array",
    fusionReason: { toString: "not callable" },
    fusionScore: { toString: "not callable" },
    unrecognizedPayload: "should not enter UI state",
  })

  assert.ok(parsed)
  assert.equal(parsed.weaponLabels, undefined)
  assert.equal(parsed.fusionReason, undefined)
  assert.equal(parsed.fusionScore, undefined)
  assert.equal("unrecognizedPayload" in parsed, false)
})

test("countBy treats prototype-like camera IDs as ordinary keys", async () => {
  const { countsByCamera } = await import("../sentinel-selectors.ts")
  const counts = countsByCamera([makeAlert("a", "__proto__", "high", 1)])
  assert.equal(counts["__proto__"], 1)
  assert.equal(Object.getPrototypeOf(counts), Object.prototype)
})

test("person detection counts accept only non-negative safe integers", () => {
  assert.equal(parsePersonCountEnvelope({ type: "person_detection", personCount: 0 }), 0)
  for (const personCount of [-1, 1.5, Number.MAX_SAFE_INTEGER + 1, "3"]) {
    assert.equal(parsePersonCountEnvelope({ type: "person_detection", personCount }), null)
  }
})


test("confirmed alert preserves source-specific score provenance and measured geometry", () => {
  const parsed = parseAlertEnvelope({
    ...makeAlert("a", "CAM-01", "high", 1),
    confirmedAlert: true, alertState: "CONFIRMED", scoreSource: "violence",
    rawModelScore: .9, rawModelConfidence: .9, calibratedProbability: .72,
    calibrationStatus: "calibrated-candidate", scoreSemantics: { rawModelScore: "untransformed producer score" },
    weaponBbox: [12, 24, 32, 64], violenceBbox: [.1, .2, .6, .7], alertVideoWidth: 640, alertVideoHeight: 480,
  })
  assert.equal(parsed.rawModelScore, .9)
  assert.equal(parsed.calibratedProbability, .72)
  assert.equal(parsed.calibrationStatus, "calibrated-candidate")
  assert.equal(parsed.scoreSource, "violence")
  assert.equal(parsed.confirmedAlert, true)
  assert.equal(parsed.scoreSemantics.rawModelScore, "untransformed producer score")
  assert.deepEqual(parsed.weaponBbox, [12, 24, 32, 64])
  assert.equal(parsed.alertVideoWidth, 640)
})

test("unavailable or invalid calibration never becomes a probability", () => {
  const valid = makeAlert("a", "CAM-01", "high", 1)
  for (const patch of [
    { calibrationStatus: "unverified", calibratedProbability: .9 },
    { calibrationStatus: "calibrated", calibratedProbability: null },
    { calibrationStatus: "calibrated", calibratedProbability: 9 },
    { calibrationStatus: "calibrated", calibratedProbability: "0.9" },
  ]) {
    const parsed = parseAlertEnvelope({ ...valid, rawModelScore: null, ...patch })
    assert.equal(parsed.calibratedProbability, null)
    assert.equal(parsed.calibrationStatus, "unverified")
    assert.equal(parsed.rawModelScore, null)
  }
})

test("rejected observations and malformed boxes cannot become incident overlays", () => {
  const valid = makeAlert("a", "CAM-01", "high", 1)
  assert.equal(parseAlertEnvelope({ ...valid, confirmedAlert: false }), null)
  assert.equal(parseAlertEnvelope({ ...valid, alertState: "WATCH" }), null)
  for (const box of [[1, 2, 0, 3], [0, 0, Infinity, 2], [0, 0, 1], [0, 0, 1, 1, 2]]) {
    assert.equal(parseAlertEnvelope({ ...valid, weaponBbox: box }).weaponBbox, undefined)
  }
})
