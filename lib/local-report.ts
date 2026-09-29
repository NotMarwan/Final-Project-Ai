import type { LiveAlert } from "@/components/video-player"

export type LocalEvidenceReport = { alertId: string; mode: "local-evidence-summary"; report: string }

type IncidentMetricInput = Partial<Pick<LiveAlert, "fusionScore" | "weaponScore" | "motionScore" | "alertLatencyMs" | "weaponLabels">>

/** Keep absent or invalid measurements distinct from an observed zero. */
export function incidentEvidenceFacts(alert: IncidentMetricInput) {
  const percent = (value: unknown) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null
  const latency = alert.alertLatencyMs
  return {
    fusion: percent(alert.fusionScore),
    weapon: percent(alert.weaponScore),
    motion: percent(alert.motionScore),
    latencyMs: typeof latency === "number" && Number.isFinite(latency) && latency >= 0 ? latency : null,
    weaponLabels: Array.isArray(alert.weaponLabels)
      ? [...new Set(alert.weaponLabels.filter((label): label is string => typeof label === "string" && Boolean(label.trim())).map((label) => label.trim()))]
      : [],
  }
}

export type EvidenceChainRecord = {
  alertId: string
  timestamp: string
  prevHash: string
  currentHash: string
  clipSha256: string | null
  snapshotSha256: string | null
  reportSha256: string | null
}

/** Parse the authenticated ledger response without displaying paths or unchecked fields. */
export function parseEvidenceChainRecord(value: unknown, alertId: string): EvidenceChainRecord | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  const hash = (candidate: unknown) => typeof candidate === "string" && /^[a-f0-9]{64}$/i.test(candidate)
  const asset = (candidate: unknown) => candidate === "N/A" ? null : hash(candidate) ? candidate as string : undefined
  const clipSha256 = asset(record.clipSha256)
  const snapshotSha256 = asset(record.snapshotSha256)
  const reportSha256 = asset(record.reportSha256)
  if (record.alertId !== alertId || typeof record.timestamp !== "string" || !Number.isFinite(Date.parse(record.timestamp))
    || !(record.prevHash === "GENESIS" || hash(record.prevHash)) || !hash(record.currentHash)
    || clipSha256 === undefined || snapshotSha256 === undefined || reportSha256 === undefined) return null
  return {
    alertId, timestamp: record.timestamp, prevHash: record.prevHash as string, currentHash: record.currentHash as string,
    clipSha256, snapshotSha256, reportSha256,
  }
}

export function parseLocalEvidenceReport(value: unknown, alertId: string): LocalEvidenceReport | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const data = value as Record<string, unknown>
  if (data.alertId !== alertId || data.mode !== "local-evidence-summary"
    || typeof data.report !== "string" || !data.report.trim() || data.report.length > 100_000) return null
  return { alertId, mode: "local-evidence-summary", report: data.report }
}
