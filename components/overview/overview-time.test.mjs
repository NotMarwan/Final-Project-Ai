import assert from "node:assert/strict"
import test from "node:test"
import { inTimeWindow, makeTimeline, windowForBuckets } from "./overview-time.ts"

const now = Date.parse("2026-09-26T05:00:00Z")
const alert = (minute, cameraId = "CAM-01", severity = "high") => ({
  id: `${cameraId}-${minute}`, cameraId, severity, type: "Weapon",
  isoTime: new Date(now - minute * 60_000).toISOString(),
})

test("timeline includes the newest boundary and excludes events outside the range", () => {
  const timeline = makeTimeline([alert(0), alert(10), alert(61)], "1h", now)
  assert.equal(timeline.buckets.reduce((sum, bucket) => sum + bucket.alerts.length, 0), 2)
  assert.equal(timeline.buckets.at(-1).alerts[0].id, "CAM-01-0")
})

test("brush returns ordered, inclusive bucket bounds", () => {
  const timeline = makeTimeline([alert(3), alert(35)], "1h", now)
  const leftToRight = windowForBuckets(timeline.buckets, 1, 4)
  assert.deepEqual(windowForBuckets(timeline.buckets, 4, 1), leftToRight)
  assert.equal(leftToRight.from, timeline.buckets[1].from)
  assert.equal(leftToRight.to, timeline.buckets[4].to)
})

test("all-session timeline never labels absent history as an incident", () => {
  const timeline = makeTimeline([], "all", now)
  assert.equal(timeline.buckets.length, 8)
  assert.ok(timeline.buckets.every((bucket) => bucket.alerts.length === 0))
})

test("step counts are 5 / 6 / 8 per range with exact epoch durations", () => {
  const cases = [["15m", 5, 15 * 60_000], ["1h", 6, 60 * 60_000], ["24h", 8, 24 * 60 * 60_000]]
  for (const [range, steps, duration] of cases) {
    const timeline = makeTimeline([], range, now)
    assert.equal(timeline.buckets.length, steps, range)
    assert.equal(timeline.from, now - duration, range)
    assert.equal(timeline.to, now, range)
    for (let index = 1; index < timeline.buckets.length; index += 1) {
      assert.equal(timeline.buckets[index].from, timeline.buckets[index - 1].to, `${range} bucket ${index}`)
    }
  }
})

test("an alert exactly on an interior bucket boundary draws in the later bucket", () => {
  const timeline = makeTimeline([alert(30)], "1h", now) // exactly the 6-bucket midpoint
  const middle = timeline.buckets[3].from
  const boundaryAlert = { id: "boundary", cameraId: "CAM-01", severity: "high", type: "Weapon", isoTime: new Date(middle).toISOString() }
  const withBoundary = makeTimeline([alert(30), boundaryAlert], "1h", now)
  assert.equal(withBoundary.buckets[3].alerts.some((item) => item.id === "boundary"), true)
  assert.equal(withBoundary.buckets[2].alerts.some((item) => item.id === "boundary"), false)
})

test("a single-bucket brush window is closed and can include the shared boundary instant", () => {
  const timeline = makeTimeline([], "1h", now)
  const boundary = timeline.buckets[2].to
  const boundaryAlert = { id: "boundary", cameraId: "CAM-01", severity: "high", type: "Weapon", isoTime: new Date(boundary).toISOString() }
  const window = windowForBuckets(timeline.buckets, 2, 2)
  // Documented boundary semantics (D8): brush windows are closed [from, to], so the
  // shared boundary instant is included by either neighbouring brush.
  assert.equal(inTimeWindow(boundaryAlert, window), true)
  assert.equal(inTimeWindow(boundaryAlert, windowForBuckets(timeline.buckets, 3, 3)), true)
})

test("inTimeWindow is closed at both ends and rejects unparseable times", () => {
  const window = { from: now - 60_000, to: now }
  const atStart = { id: "s", cameraId: "CAM-01", severity: "high", type: "Weapon", isoTime: new Date(window.from).toISOString() }
  const atEnd = { id: "e", cameraId: "CAM-01", severity: "high", type: "Weapon", isoTime: new Date(window.to).toISOString() }
  assert.equal(inTimeWindow(atStart, window), true)
  assert.equal(inTimeWindow(atEnd, window), true)
  assert.equal(inTimeWindow({ ...atStart, isoTime: "nonsense" }, window), false)
})

test("all-session span grows with the oldest alert but never below one hour", () => {
  const wide = makeTimeline([alert(90), alert(5)], "all", now)
  assert.equal(wide.from, now - 90 * 60_000 - 1)
  const span = wide.to - wide.from
  assert.ok(span >= 60 * 60_000)
  assert.ok(span <= 91 * 60_000)
  const recent = makeTimeline([alert(5)], "all", now)
  assert.equal(recent.to - recent.from, 60 * 60_000) // minimum one hour
})

test("windows are DST-safe: identical wall clocks, distinct instants", () => {
  // US fall-back 2026-11-01: 01:30 local happens twice, one hour apart as instants.
  const dstNow = Date.parse("2026-11-01T07:00:00Z")
  const first = { id: "first", cameraId: "CAM-01", severity: "high", type: "Weapon", isoTime: "2026-11-01T01:30:00-04:00" }  // 05:30Z
  const second = { id: "second", cameraId: "CAM-01", severity: "high", type: "Weapon", isoTime: "2026-11-01T01:30:00-05:00" } // 06:30Z
  // The 1h window [06:00Z, 07:00Z] contains only the later 01:30 instant.
  const oneHour = makeTimeline([first, second], "1h", dstNow)
  assert.deepEqual(oneHour.buckets.flatMap((bucket) => bucket.alerts.map((item) => item.id)), ["second"])
  // The 24h window contains both, ordered by instant.
  const day = makeTimeline([first, second], "24h", dstNow)
  assert.equal(day.buckets.reduce((sum, bucket) => sum + bucket.alerts.length, 0), 2)
  const firstBucket = day.buckets.findIndex((bucket) => bucket.alerts.some((item) => item.id === "first"))
  const secondBucket = day.buckets.findIndex((bucket) => bucket.alerts.some((item) => item.id === "second"))
  assert.ok(firstBucket <= secondBucket)
})
