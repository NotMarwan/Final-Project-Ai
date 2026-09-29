"use client"

// WT-26 (S-13): persisted statistics source for the overview. Aggregates the
// backend evidence ledger via the additive GET /stats/overview route and falls
// back gracefully to session-scoped data (always labeled). The payload counts
// EVIDENCE RECORDS timestamped at evidence-write time — never raw alert
// occurrence counts. See docs/campaign/engineering/26-stats-semantics.md §2.2.

import { useEffect, useMemo, useState } from "react"
import { apiFetch } from "@/lib/api-auth"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

export type StatsSource = "persisted" | "session"

export type OverviewStatsWindow = { from: string; to: string; recordCount: number }

export type OverviewStatsPayload = {
  scope: string
  timeField: string
  window: { from: string; to: string }
  cameraId: string | null
  recordCount: number
  bySeverity: { critical: number; high: number; medium: number; other: number }
  byCamera: Record<string, number>
  typeBreakdown: null
  latency: null
  previousWindow: OverviewStatsWindow | null
  ledger: { path: string; exists: boolean; totalRecords: number }
  generatedAt: string
}

export type OverviewStatsState =
  | { status: "loading" }
  | { status: "persisted"; payload: OverviewStatsPayload }
  | { status: "fallback"; reason: "offline" | "server-error" | "invalid-payload" | "fixture" }

function boundedRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function nonNegative(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null
}

function parseWindow(value: unknown): OverviewStatsWindow | null {
  if (!boundedRecord(value)) return null
  const recordCount = nonNegative(value.recordCount)
  if (typeof value.from !== "string" || typeof value.to !== "string" || recordCount === null) return null
  return { from: value.from, to: value.to, recordCount }
}

export function parseOverviewStatsPayload(data: unknown): OverviewStatsPayload | null {
  if (!boundedRecord(data)) return null
  const recordCount = nonNegative(data.recordCount)
  const severity = data.bySeverity
  const ledger = data.ledger
  if (data.scope !== "evidence-ledger" || recordCount === null
    || !boundedRecord(data.window) || typeof data.window.from !== "string" || typeof data.window.to !== "string"
    || !boundedRecord(severity) || !boundedRecord(ledger) || typeof data.timeField !== "string"
    || typeof data.generatedAt !== "string") return null
  const byCamera: Record<string, number> = {}
  if (boundedRecord(data.byCamera)) {
    for (const [cameraId, count] of Object.entries(data.byCamera)) {
      const parsed = nonNegative(count)
      if (parsed !== null && cameraId.length > 0 && cameraId.length <= 128) byCamera[cameraId] = parsed
    }
  }
  return {
    scope: "evidence-ledger",
    timeField: data.timeField,
    window: { from: data.window.from, to: data.window.to },
    cameraId: typeof data.cameraId === "string" && data.cameraId ? data.cameraId : null,
    recordCount,
    bySeverity: {
      critical: nonNegative(severity.critical) ?? 0,
      high: nonNegative(severity.high) ?? 0,
      medium: nonNegative(severity.medium) ?? 0,
      other: nonNegative(severity.other) ?? 0,
    },
    byCamera,
    typeBreakdown: null,
    latency: null,
    previousWindow: data.previousWindow === null ? null : parseWindow(data.previousWindow),
    ledger: {
      path: typeof ledger.path === "string" ? ledger.path : "",
      exists: ledger.exists === true,
      totalRecords: nonNegative(ledger.totalRecords) ?? 0,
    },
    generatedAt: data.generatedAt,
  }
}

export function useOverviewStats({ from, to, cameraId, enabled }: {
  from: number
  to: number
  cameraId?: string
  enabled: boolean
}): OverviewStatsState {
  const [state, setState] = useState<OverviewStatsState>({ status: "loading" })
  // Quantise the moving window to the minute so the 15s clock tick does not refetch.
  const windowKey = useMemo(() => `${Math.floor(from / 60_000)}:${Math.floor(to / 60_000)}:${cameraId ?? ""}`, [from, to, cameraId])

  useEffect(() => {
    if (!enabled) {
      setState({ status: "fallback", reason: "fixture" })
      return
    }
    const controller = new AbortController()
    setState({ status: "loading" })
    const query = new URLSearchParams({ from: new Date(from).toISOString(), to: new Date(to).toISOString() })
    if (cameraId) query.set("cameraId", cameraId)
    void (async () => {
      try {
        const response = await apiFetch(`${API_BASE}/stats/overview?${query.toString()}`, { signal: controller.signal })
        if (!response.ok) {
          setState({ status: "fallback", reason: "server-error" })
          return
        }
        const payload = parseOverviewStatsPayload(await response.json())
        if (!payload) {
          setState({ status: "fallback", reason: "invalid-payload" })
          return
        }
        setState({ status: "persisted", payload })
      } catch {
        if (!controller.signal.aborted) setState({ status: "fallback", reason: "offline" })
      }
    })()
    return () => controller.abort()
  }, [windowKey, enabled])

  return state
}
