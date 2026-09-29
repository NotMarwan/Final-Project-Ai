import assert from "node:assert/strict"
import test from "node:test"
import {
  SESSION_ALERT_CAP,
  chartDimensionSets,
  confidenceBandIndex,
  confidenceHistogram,
  parseAlertEnvelope,
  parsePersonCountEnvelope,
  previousWindowComparison,
  sessionCoverage,
} from "../sentinel-selectors.ts"

const now = Date.parse("2026-09-26T12:00:00.000Z")
const alert = (id, minutesAgo, overrides = {}) => ({
  id, cameraId: "CAM-01", severity: "high", type: "Weapon", confidence: 80,
  location: "اختبار", timestamp: "12:00", isoTime: new Date(now - minutesAgo * 60_000).toISOString(),
  ...overrides,
})

// ── confidence bands ────────────────────────────────────────────────────────

test("confidence band index maps score edges exactly as the histogram does", () => {
  assert.equal(confidenceBandIndex(0), 0)
  assert.equal(confidenceBandIndex(19.999), 0)
  assert.equal(confidenceBandIndex(20), 1)
  assert.equal(confidenceBandIndex(99.999), 4)
  assert.equal(confidenceBandIndex(100), 4)
  const alerts = [0, 19.999, 20, 79.9, 100].map((confidence, index) => alert(`b${index}`, 1, { confidence }))
  const histogram = confidenceHistogram(alerts)
  assert.deepEqual(histogram.map((band) => band.count), [2, 1, 0, 1, 1])
  for (const item of alerts) {
    assert.equal(histogram[confidenceBandIndex(item.confidence)].count > 0, true)
  }
})

// ── session coverage ────────────────────────────────────────────────────────

test("session coverage reports the observed span and the cap flag", () => {
  const three = [alert("a", 1), alert("b", 5), alert("c", 9)]
  const coverage = sessionCoverage(three)
  assert.equal(coverage.observedFrom, now - 9 * 60_000)
  assert.equal(coverage.observedTo, now - 60_000)
  assert.equal(coverage.capped, false)
  assert.equal(sessionCoverage(Array.from({ length: SESSION_ALERT_CAP }, (_, i) => alert(`c${i}`, i))).capped, true)
  const empty = sessionCoverage([])
  assert.deepEqual(empty, { observedFrom: null, observedTo: null, capped: false })
})

test("session coverage ignores unparseable timestamps", () => {
  const coverage = sessionCoverage([alert("a", 4), { ...alert("x", 0), isoTime: "not-a-time" }])
  assert.equal(coverage.observedFrom, now - 4 * 60_000)
  assert.equal(coverage.observedTo, now - 4 * 60_000)
})

// ── previous-window comparison (denominator honesty) ────────────────────────

test("no comparison baseline exists for the session-wide range or an empty session", () => {
  assert.deepEqual(previousWindowComparison([alert("a", 1)], { range: "all" }, now), { available: false, reason: "all-range" })
  assert.deepEqual(previousWindowComparison([], { range: "1h" }, now), { available: false, reason: "empty-session" })
})

test("previous window is half-open [now-2d, now-d) and applies the same dimension filters", () => {
  const alerts = [
    alert("in-window", 90),            // 90 min ago → inside previous 1h window [120, 60) minutes ago
    alert("on-upper-boundary", 60),    // exactly now-d → belongs to the CURRENT window, not the previous
    alert("on-lower-boundary", 120),   // exactly now-2d → inside the previous window (>=)
    alert("too-old", 121),
    alert("wrong-camera", 90, { cameraId: "CAM-02" }),
  ]
  const comparison = previousWindowComparison(alerts, { range: "1h", cameraId: "CAM-01" }, now)
  assert.equal(comparison.available, true)
  assert.equal(comparison.previousCount, 2)
  assert.deepEqual(comparison.window, { from: now - 120 * 60_000, to: now - 60 * 60_000 })
})

test("baseline is refused when session start leaves the previous window unobserved", () => {
  // Session began 20 minutes ago; the previous 1h window lies almost entirely before it.
  const alerts = [alert("a", 20), alert("b", 2)]
  assert.deepEqual(previousWindowComparison(alerts, { range: "1h" }, now), { available: false, reason: "outside-session-coverage" })
})

test("baseline is refused when the 50-alert cap evicted the previous window", () => {
  // Full buffer whose oldest alert is 10 minutes old → the previous window is gone.
  const alerts = Array.from({ length: SESSION_ALERT_CAP }, (_, i) => alert(`c${i}`, i / 5))
  assert.equal(alerts.length, SESSION_ALERT_CAP)
  assert.deepEqual(previousWindowComparison(alerts, { range: "1h" }, now), { available: false, reason: "outside-session-coverage" })
})

test("baseline is available when the session observed the whole previous window", () => {
  const alerts = [alert("old", 200), alert("prev-1", 90), alert("prev-2", 70), alert("cur", 5)]
  const comparison = previousWindowComparison(alerts, { range: "1h" }, now)
  assert.equal(comparison.available, true)
  assert.equal(comparison.previousCount, 2)
})

test("brushed views compare against the same brush shifted back one duration", () => {
  const brush = { from: now - 30 * 60_000, to: now - 10 * 60_000 }
  const alerts = [
    alert("brush-current", 20),
    alert("brush-previous", 20 + 60),   // same offset one hour earlier → shifted brush
    alert("shifted-neighbour", 25 + 60), // inside shifted window ([90,70] minutes ago closed)
    alert("outside", 50 + 60),
  ]
  const comparison = previousWindowComparison(alerts, { range: "1h" }, now, brush)
  assert.equal(comparison.available, true)
  assert.equal(comparison.previousCount, 2)
  assert.deepEqual(comparison.window, { from: brush.from - 60 * 60_000, to: brush.to - 60 * 60_000 })
})

// ── chart dimension composition (cross-filter isolation) ────────────────────

test("each chart drops only its own dimension and keeps the others", () => {
  const alerts = [
    alert("a", 5, { cameraId: "CAM-01", severity: "critical", type: "Weapon", confidence: 90 }),
    alert("b", 5, { cameraId: "CAM-02", severity: "high", type: "Violence", confidence: 30 }),
    alert("c", 5, { cameraId: "CAM-01", severity: "medium", type: "Violence", confidence: 55 }),
    alert("d", 70, { cameraId: "CAM-01", severity: "high", type: "Weapon", confidence: 95 }),
  ]
  const filters = { range: "1h", cameraId: "CAM-01", type: "Violence", severity: "medium", confidenceBand: 2 }
  const sets = chartDimensionSets(alerts, filters, now)
  // camera set: cameraId dropped → a, b, c pass the remaining type/severity/band filters? only c matches all but camera.
  assert.deepEqual(sets.camera.map((item) => item.id), ["c"])
  // severity set: severity dropped → c (Violence, CAM-01, band 2) only; a is Weapon, b is CAM-02.
  assert.deepEqual(sets.severity.map((item) => item.id), ["c"])
  // confidence set: band dropped → c only (Violence + CAM-01 + medium).
  assert.deepEqual(sets.confidence.map((item) => item.id), ["c"])
  // timeline: cameraId + type dropped, severity + band kept → c only (within the 1h range).
  assert.deepEqual(sets.timeline.map((item) => item.id), ["c"])
  // context: range only → a, b, c (d is outside the 1h range).
  assert.deepEqual(sets.context.map((item) => item.id).sort(), ["a", "b", "c"])
})

test("the brush filters camera/severity/confidence sets but never the timeline or context", () => {
  const alerts = [
    alert("in-brush", 5),
    alert("out-of-brush", 45),
  ]
  const brush = { from: now - 10 * 60_000, to: now }
  const filters = { range: "1h" }
  const sets = chartDimensionSets(alerts, filters, now, brush)
  assert.deepEqual(sets.camera.map((item) => item.id), ["in-brush"])
  assert.deepEqual(sets.severity.map((item) => item.id), ["in-brush"])
  assert.deepEqual(sets.confidence.map((item) => item.id), ["in-brush"])
  assert.deepEqual(sets.timeline.map((item) => item.id).sort(), ["in-brush", "out-of-brush"])
  assert.deepEqual(sets.context.map((item) => item.id).sort(), ["in-brush", "out-of-brush"])
})

test("a brush end boundary is closed like the overview brush filter", () => {
  const boundary = now - 10 * 60_000
  const alerts = [{ ...alert("on-boundary", 10), isoTime: new Date(boundary).toISOString() }]
  const sets = chartDimensionSets(alerts, { range: "1h" }, now, { from: boundary, to: now })
  assert.deepEqual(sets.camera.map((item) => item.id), ["on-boundary"])
})

// ── DST / timezone edge cases (epoch arithmetic must be exact) ──────────────

test("range windows are exact epoch durations across a DST fall-back", () => {
  // US fall-back 2026-11-01: wall clock 01:30 occurs twice — first as -04:00 (05:30Z),
  // then as -05:00 (06:30Z). Window math must use instants, never wall clocks.
  const first0130 = "2026-11-01T01:30:00-04:00"
  const second0130 = "2026-11-01T01:30:00-05:00"
  const dstNow = Date.parse("2026-11-01T07:00:00Z")
  const alerts = [
    { ...alert("first", 0), isoTime: first0130 },
    { ...alert("second", 0), isoTime: second0130 },
    { ...alert("old", 0), isoTime: "2026-10-31T23:30:00-04:00" }, // 03:30Z
  ]
  assert.equal(Date.parse(second0130) - Date.parse(first0130), 60 * 60_000)
  // The 1h window [06:00Z, 07:00Z] contains only the later 01:30 instant.
  const sets = chartDimensionSets(alerts, { range: "1h" }, dstNow)
  assert.deepEqual(sets.context.map((item) => item.id), ["second"])
  // The previous window [05:00Z, 06:00Z) contains the earlier 01:30 instant.
  const comparison = previousWindowComparison(alerts, { range: "1h" }, dstNow)
  assert.equal(comparison.available, true)
  assert.equal(comparison.previousCount, 1)
})

test("previous-window math stays exact across a DST spring-forward", () => {
  // US spring-forward 2026-03-08: 02:00–03:00 local does not exist; instants still do.
  assert.equal(Date.parse("2026-03-08T05:00:00-05:00"), Date.parse("2026-03-08T10:00:00Z"))
  const dstNow = Date.parse("2026-03-08T11:10:00Z")
  const alerts = [
    { ...alert("prev", 0), isoTime: "2026-03-08T05:00:00-05:00" }, // 10:00Z
    { ...alert("cur", 0), isoTime: "2026-03-08T07:00:00-04:00" },  // 11:00Z
  ]
  const comparison = previousWindowComparison(alerts, { range: "15m" }, dstNow)
  // Observed from 10:00Z; previous 15m window [10:40Z, 10:55Z) is fully observed but empty.
  assert.equal(comparison.available, true)
  assert.equal(comparison.previousCount, 0)
  // The current window [10:55Z, 11:10Z] holds the 11:00Z alert.
  assert.deepEqual(chartDimensionSets(alerts, { range: "15m" }, dstNow).context.map((item) => item.id), ["cur"])
})

// ── unit discipline (S26-1): person readings are not alerts ─────────────────

test("person-count envelopes never enter the alert stream", () => {
  assert.equal(parsePersonCountEnvelope({ type: "person_detection", personCount: 3 }), 3)
  assert.equal(parseAlertEnvelope({ type: "person_detection", personCount: 3 }), null)
})
