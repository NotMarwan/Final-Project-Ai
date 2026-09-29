import assert from "node:assert/strict"
import { test } from "node:test"
import { CATEGORY_LABELS, formatAlertRelativeArabic, minuteHeatBuckets } from "../../lib/detection-types.ts"

test("category labels are Arabic while wire IDs remain stable", () => {
  assert.equal(CATEGORY_LABELS.weapon, "سلاح")
  assert.equal(CATEGORY_LABELS.violence, "اعتداء")
})

test("relative alert time is Arabic and handles invalid or future timestamps", () => {
  const now = Date.parse("2026-09-26T12:00:00Z")
  assert.equal(formatAlertRelativeArabic("2026-09-26T11:58:00Z", now), "قبل دقيقتين")
  assert.equal(formatAlertRelativeArabic("2026-09-26T12:01:00Z", now), "الآن")
  assert.equal(formatAlertRelativeArabic("invalid", now), "وقت غير متاح")
})

test("minute histogram counts only received alerts in the selected window", () => {
  const now = Date.parse("2026-09-26T12:00:00Z")
  const alerts = [
    { isoTime: "2026-09-26T11:59:30Z", severity: "critical" },
    { isoTime: "2026-09-26T11:59:10Z", severity: "high" },
    { isoTime: "2026-09-26T11:57:00Z", severity: "medium" },
    { isoTime: "2026-09-26T12:01:00Z", severity: "critical" },
  ]
  assert.deepEqual(minuteHeatBuckets(alerts, now, 4).map(({ total, critical }) => [total, critical]), [[0, 0], [1, 0], [0, 0], [2, 1]])
})
