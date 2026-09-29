"use client"

import { useState, useCallback } from "react"
import {
  MapPin,
  Camera,
  Clock,
  Crosshair,
  ShieldAlert,
  XCircle,
  Download,
  ChevronRight,
  ShieldCheck,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { LiveAlert } from "@/components/video-player"

// ─── Config ───────────────────────────────────────────────────────────────────

const API_BASE = "http://localhost:8000"

/**
 * How many times to retry GET /download_evidence while the server responds
 * with HTTP 202 (clip is still being compiled).
 */
const MAX_POLL_ATTEMPTS = 20
const POLL_INTERVAL_MS  = 1_500   // 1.5 s between retries  → 30 s max wait

// ─── Export button states ─────────────────────────────────────────────────────

type ExportState =
  | { phase: "idle" }
  | { phase: "polling"; attempt: number }
  | { phase: "downloading" }
  | { phase: "done" }
  | { phase: "error"; message: string }

// ─── Props ────────────────────────────────────────────────────────────────────

interface IncidentPanelProps {
  alert: LiveAlert | null
}

// ─── Component ────────────────────────────────────────────────────────────────

export function IncidentPanel({ alert }: IncidentPanelProps) {
  const [exportState, setExportState] = useState<ExportState>({ phase: "idle" })

  // Reset export state whenever the active alert changes
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const alertId = alert?.id

  // ── Dispatch handler ───────────────────────────────────────────────────────
  const handleDispatch = useCallback(() => {
    if (!alert) return
    window.alert(`🚨 Security Team Dispatched to ${alert.cameraId}!`)
  }, [alert])

  // ── False alarm handler ────────────────────────────────────────────────────
  const handleFalseAlarm = useCallback(() => {
    window.alert("✅ Incident marked as false alarm and logged.")
  }, [])

  // ── Evidence export handler ────────────────────────────────────────────────
  /**
   * Flow:
   *  1. Send GET /download_evidence/<alert_id>
   *  2. If 202 → clip still compiling; wait POLL_INTERVAL_MS and retry.
   *  3. If 200 → blob response; trigger browser Save-As dialogue.
   *  4. Any other status or network failure → show error message.
   *
   * The download runs entirely in the browser — no new library needed.
   */
  const handleExportEvidence = useCallback(async () => {
    if (!alert) return
    if (exportState.phase !== "idle" && exportState.phase !== "done" && exportState.phase !== "error") {
      return  // prevent double-click while in progress
    }

    setExportState({ phase: "polling", attempt: 1 })

    for (let attempt = 1; attempt <= MAX_POLL_ATTEMPTS; attempt++) {
      try {
        const res = await fetch(
          `${API_BASE}/download_evidence/${alert.id}`
        )

        // ── Still compiling ──────────────────────────────────────────────
        if (res.status === 202) {
          if (attempt >= MAX_POLL_ATTEMPTS) {
            setExportState({
              phase:   "error",
              message: "Server is taking too long to compile the clip. Try again later.",
            })
            return
          }
          setExportState({ phase: "polling", attempt: attempt + 1 })
          await _sleep(POLL_INTERVAL_MS)
          continue
        }

        // ── Server error ─────────────────────────────────────────────────
        if (!res.ok) {
          let detail = `Server error ${res.status}`
          try {
            const body = await res.json()
            if (body?.detail) detail = body.detail
          } catch { /* ignore */ }
          setExportState({ phase: "error", message: detail })
          return
        }

        // ── Ready — trigger browser download ─────────────────────────────
        setExportState({ phase: "downloading" })
        const blob     = await res.blob()
        const blobUrl  = URL.createObjectURL(blob)
        const anchor   = document.createElement("a")
        anchor.href     = blobUrl
        anchor.download = `${alert.id}.mp4`
        document.body.appendChild(anchor)
        anchor.click()
        document.body.removeChild(anchor)
        // Revoke after a short delay to let the download start
        setTimeout(() => URL.revokeObjectURL(blobUrl), 5_000)

        setExportState({ phase: "done" })
        // Auto-reset the button label after 4 s so it can be re-used
        setTimeout(
          () => setExportState({ phase: "idle" }),
          4_000
        )
        return

      } catch (err) {
        // Network-level failure (CORS, API offline, etc.)
        setExportState({
          phase:   "error",
          message: err instanceof Error ? err.message : "Network error — is the API running?",
        })
        return
      }
    }
  }, [alert, exportState.phase])

  // ── Render: no alert selected yet ─────────────────────────────────────────
  if (!alert) return <NoIncidentState />

  // ── Render: active incident ────────────────────────────────────────────────
  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3">

      {/* ── Incident Details ──────────────────────────────────────────── */}
      <div className="rounded-lg border border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <Crosshair className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">
            Incident Details
          </span>
          <Badge
            className={cn(
              "ml-auto h-5 border px-1.5 font-mono text-[9px] uppercase",
              alert.severity === "critical"
                ? "border-danger/30 bg-danger/20 text-danger"
                : alert.severity === "high"
                ? "border-warning/30 bg-warning/20 text-warning"
                : "border-primary/30 bg-primary/20 text-primary"
            )}
          >
            {alert.severity}
          </Badge>
        </div>

        <div className="flex flex-col gap-2.5 p-3">
          <MetadataRow
            icon={<Camera className="h-3.5 w-3.5" />}
            label="Camera"
            value={`${alert.cameraId} — ${alert.location}`}
          />
          <MetadataRow
            icon={<Clock className="h-3.5 w-3.5" />}
            label="Detected At"
            value={alert.timestamp}
          />
          <MetadataRow
            icon={<Crosshair className="h-3.5 w-3.5" />}
            label="Event Type"
            value="Violence Detected"
          />

          {/* Confidence bar */}
          <div className="mt-1 rounded-md bg-secondary/50 p-2">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Model Confidence
              </span>
              <span className="font-mono text-[11px] font-semibold text-danger">
                {alert.confidence.toFixed(1)}%
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  alert.severity === "critical"
                    ? "bg-danger"
                    : alert.severity === "high"
                    ? "bg-warning"
                    : "bg-primary"
                )}
                style={{ width: `${alert.confidence}%` }}
              />
            </div>
          </div>

          {/* AI summary */}
          <div className="rounded-md bg-danger/5 p-2">
            <p className="text-[11px] leading-relaxed text-muted-foreground">
              The AI model detected{" "}
              <span className="font-semibold text-foreground">violent behaviour</span> on
              camera{" "}
              <span className="font-mono text-primary">{alert.cameraId}</span> with{" "}
              <span className="font-semibold text-danger">
                {alert.confidence.toFixed(1)}% confidence
              </span>
              . Severity assessed as{" "}
              <span className="font-semibold capitalize">{alert.severity}</span>.
            </p>
          </div>
        </div>
      </div>

      {/* ── Approximate location map ──────────────────────────────────── */}
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2">
          <MapPin className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">Camera Location</span>
        </div>
        <div className="p-3">
          <svg viewBox="0 0 100 70" className="w-full" aria-label="Schematic floor plan">
            {/* Building shell */}
            <rect
              x="5" y="5" width="90" height="60" rx="1"
              fill="none" stroke="#334155" strokeWidth="0.5"
            />
            {/* Zone grid */}
            {[
              { x: 5,  y: 5,  w: 30, h: 30, label: "Zone A" },
              { x: 35, y: 5,  w: 30, h: 30, label: "Zone B" },
              { x: 65, y: 5,  w: 30, h: 30, label: "Zone C" },
              { x: 5,  y: 35, w: 45, h: 30, label: "Zone D" },
              { x: 50, y: 35, w: 45, h: 30, label: "Zone E" },
            ].map((r) => (
              <g key={r.label}>
                <rect
                  x={r.x} y={r.y} width={r.w} height={r.h} rx="0.5"
                  fill="rgba(30,41,59,0.5)" stroke="#334155" strokeWidth="0.3"
                />
                <text
                  x={r.x + r.w / 2} y={r.y + r.h / 2 + 1}
                  textAnchor="middle" fontSize="3" fontFamily="monospace"
                  fill="#64748b"
                >
                  {r.label}
                </text>
              </g>
            ))}
            {/* Pulsing camera pin — anchored to Zone A for CAM-01 */}
            <circle cx="20" cy="20" r="5" fill="rgba(239,68,68,0.15)">
              <animate attributeName="r"       values="3;7;3"     dur="2s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.5;0;0.5" dur="2s" repeatCount="indefinite" />
            </circle>
            <circle
              cx="20" cy="20" r="2.5"
              fill="#ef4444" stroke="#0f172a" strokeWidth="0.5"
            />
            <text
              x="20" y="14" textAnchor="middle"
              fontSize="2.5" fontFamily="monospace" fontWeight="bold"
              fill="#ef4444"
            >
              {alert.cameraId}
            </text>
          </svg>
        </div>
      </div>

      {/* ── Action buttons ────────────────────────────────────────────── */}
      <div className="flex flex-col gap-2">

        {/* DISPATCH */}
        <Button
          onClick={handleDispatch}
          className="h-11 w-full gap-2 bg-danger font-semibold text-sm text-danger-foreground shadow-lg shadow-danger/20 transition-all hover:bg-danger/90 active:scale-[0.98]"
        >
          <ShieldAlert className="h-4 w-4" />
          DISPATCH SECURITY TEAM
          <ChevronRight className="ml-auto h-4 w-4" />
        </Button>

        <div className="flex gap-2">

          {/* FALSE ALARM */}
          <Button
            variant="secondary"
            onClick={handleFalseAlarm}
            className="h-9 flex-1 gap-1.5 bg-secondary text-xs text-secondary-foreground transition-all hover:bg-secondary/80 active:scale-[0.97]"
          >
            <XCircle className="h-3.5 w-3.5" />
            Mark False Alarm
          </Button>

          {/* EXPORT EVIDENCE */}
          <Button
            variant="outline"
            onClick={handleExportEvidence}
            disabled={
              exportState.phase === "polling" ||
              exportState.phase === "downloading"
            }
            className={cn(
              "h-9 flex-1 gap-1.5 border-border text-xs transition-all active:scale-[0.97]",
              exportState.phase === "done"
                ? "border-success/40 bg-success/10 text-success hover:bg-success/20"
                : exportState.phase === "error"
                ? "border-danger/40 bg-danger/10 text-danger hover:bg-danger/20"
                : "text-foreground hover:bg-secondary"
            )}
          >
            <ExportButtonContent state={exportState} />
          </Button>
        </div>

        {/* Error detail message (shown below buttons) */}
        {exportState.phase === "error" && (
          <p className="rounded-md border border-danger/20 bg-danger/5 px-2.5 py-1.5 text-[10px] leading-relaxed text-danger/80">
            <span className="font-semibold">Export failed:</span>{" "}
            {exportState.message}
          </p>
        )}
      </div>
    </div>
  )
}

// ─── Export button inner content ──────────────────────────────────────────────

function ExportButtonContent({ state: s }: { state: ExportState }) {
  switch (s.phase) {
    case "idle":
      return (
        <>
          <Download className="h-3.5 w-3.5" />
          Export Evidence
        </>
      )
    case "polling":
      return (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Compiling… ({s.attempt}/{MAX_POLL_ATTEMPTS})
        </>
      )
    case "downloading":
      return (
        <>
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Downloading…
        </>
      )
    case "done":
      return (
        <>
          <CheckCircle2 className="h-3.5 w-3.5" />
          Downloaded!
        </>
      )
    case "error":
      return (
        <>
          <AlertCircle className="h-3.5 w-3.5" />
          Retry Export
        </>
      )
  }
}

// ─── No-alert empty state ─────────────────────────────────────────────────────

function NoIncidentState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
      <ShieldCheck className="h-10 w-10 text-muted-foreground/30" />
      <div>
        <p className="text-sm font-medium text-muted-foreground">No Active Incident</p>
        <p className="mt-1 text-xs text-muted-foreground/60">
          Details will appear here when violence is detected.
        </p>
      </div>
    </div>
  )
}

// ─── MetadataRow ──────────────────────────────────────────────────────────────

function MetadataRow({
  icon,
  label,
  value,
}: {
  icon:  React.ReactNode
  label: string
  value: string
}) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 text-muted-foreground">{icon}</span>
      <div className="flex flex-col">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <span className="text-xs font-medium text-foreground">{value}</span>
      </div>
    </div>
  )
}

// ─── Utility ──────────────────────────────────────────────────────────────────

const _sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
