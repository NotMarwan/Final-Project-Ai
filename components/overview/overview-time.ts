import type { LiveAlert } from "@/components/video-player"
import type { Range } from "@/lib/sentinel-selectors"

export type TimeWindow = { from: number; to: number }
export type AlertTimeBucket = TimeWindow & { alerts: LiveAlert[] }

const RANGE_MS = { "15m": 15 * 60_000, "1h": 60 * 60_000, "24h": 24 * 60 * 60_000 } as const
const STEP_COUNT = { "15m": 5, "1h": 6, "24h": 8, all: 8 } as const

export function inTimeWindow(alert: LiveAlert, window: TimeWindow): boolean {
  const time = Date.parse(alert.isoTime)
  return Number.isFinite(time) && time >= window.from && time <= window.to
}

export function makeTimeline(alerts: readonly LiveAlert[], range: Range, now: number): { from: number; to: number; buckets: AlertTimeBucket[] } {
  const times = alerts.map((alert) => Date.parse(alert.isoTime)).filter((time) => Number.isFinite(time) && time <= now)
  const duration = range === "all"
    ? Math.max(RANGE_MS["1h"], now - (times.length ? Math.min(...times) : now) + 1)
    : RANGE_MS[range]
  const from = now - duration
  const count = STEP_COUNT[range]
  const size = duration / count
  const buckets = Array.from({ length: count }, (_, index) => ({
    from: from + size * index,
    to: from + size * (index + 1),
    alerts: [] as LiveAlert[],
  }))
  for (const alert of alerts) {
    const time = Date.parse(alert.isoTime)
    if (!Number.isFinite(time) || time < from || time > now) continue
    const index = Math.min(count - 1, Math.floor((time - from) / size))
    buckets[index].alerts.push(alert)
  }
  return { from, to: now, buckets }
}

export function windowForBuckets(buckets: readonly AlertTimeBucket[], first: number, last: number): TimeWindow {
  const start = Math.max(0, Math.min(buckets.length - 1, Math.min(first, last)))
  const end = Math.max(0, Math.min(buckets.length - 1, Math.max(first, last)))
  return { from: buckets[start].from, to: buckets[end].to }
}
