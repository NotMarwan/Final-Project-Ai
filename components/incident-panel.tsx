"use client"

import { useState, useCallback, useRef, useEffect } from "react"
import {
  MapPin, Camera, Clock, Crosshair,
  ShieldAlert, XCircle, Download, ChevronRight,
  ShieldCheck, Loader2, CheckCircle2, AlertCircle,
  SlidersHorizontal, CheckCheck, Info, X,
  FileSearch, Sparkles, Timer, FileDown, UserRound, ScanFace
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { LiveAlert } from "@/components/video-player"

// ─── Config ───────────────────────────────────────────────────────────────────

const API_BASE          = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const MAX_POLL_ATTEMPTS = 20
const POLL_INTERVAL_MS  = 1_500
const TOAST_DURATION_MS = 4_500
const THRESHOLD_DEBOUNCE_MS = 400

// ─── Toast system ─────────────────────────────────────────────────────────────

type ToastVariant = "success" | "info" | "error"
interface Toast { id: number; message: string; variant: ToastVariant }

// ─── Export button states ─────────────────────────────────────────────────────

type ExportPhase =
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
  const [exportState,   setExportState]   = useState<ExportPhase>({ phase: "idle" })
  const [reportState,   setReportState]   = useState<ExportPhase>({ phase: "idle" })
  const [toasts,        setToasts]        = useState<Toast[]>([])
  
  // شريط الحساسية
  const [threshold,     setThreshold]     = useState<number>(50)
  const [thresholdBusy, setThresholdBusy] = useState(false)
  
  // شريط الكولداون (Alert Timeout)
  const [cooldown,      setCooldown]      = useState<number>(60)
  const [cooldownBusy,  setCooldownBusy]  = useState(false)
  
  // Face policy controls
  const [faceIdentityLabeling, setFaceIdentityLabeling] = useState(true)
  const [faceIdentityBusy, setFaceIdentityBusy] = useState(false)
  const [faceAuditEnabled, setFaceAuditEnabled] = useState(true)
  const [faceAuditBusy, setFaceAuditBusy] = useState(false)
  const [faceAuditCooldown, setFaceAuditCooldown] = useState(25)
  const [faceAuditCooldownBusy, setFaceAuditCooldownBusy] = useState(false)

  const toastCounter        = useRef(0)
  const debounceTimerRef    = useRef<ReturnType<typeof setTimeout> | null>(null)
  const debounceCooldownRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const debounceFaceAuditCooldownRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Reset export state when a new alert arrives ────────────────────────────
  useEffect(() => {
    setExportState({ phase: "idle" })
    setReportState({ phase: "idle" })
  }, [alert?.id])

  // ── Toast helpers ──────────────────────────────────────────────────────────

  const addToast = useCallback((message: string, variant: ToastVariant = "info") => {
    const id = ++toastCounter.current
    setToasts((prev) => [...prev, { id, message, variant }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), TOAST_DURATION_MS)
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // ── Action handlers ────────────────────────────────────────────────────────

  const handleDispatch = useCallback(() => {
    if (!alert) return
    addToast(`🚨 Security team dispatched to ${alert.cameraId}!`, "success")
  }, [alert, addToast])

  const handleFalseAlarm = useCallback(() => {
    addToast("Incident marked as false alarm and logged.", "info")
  }, [addToast])

  const handleExportEvidence = useCallback(async () => {
    if (!alert) return
    if (exportState.phase !== "idle" && exportState.phase !== "done" && exportState.phase !== "error") return

    setExportState({ phase: "polling", attempt: 1 })

    for (let attempt = 1; attempt <= MAX_POLL_ATTEMPTS; attempt++) {
      try {
        const res = await fetch(`${API_BASE}/download_evidence/${alert.id}`)

        if (res.status === 202) {
          if (attempt >= MAX_POLL_ATTEMPTS) {
            setExportState({ phase: "error", message: "Server taking too long — retry later." })
            return
          }
          setExportState({ phase: "polling", attempt: attempt + 1 })
          await _sleep(POLL_INTERVAL_MS)
          continue
        }

        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          const msg  = body?.detail ?? `Server error ${res.status}`
          setExportState({ phase: "error", message: msg })
          addToast(`Export failed: ${msg}`, "error")
          return
        }

        setExportState({ phase: "downloading" })
        const blob    = await res.blob()
        const blobUrl = URL.createObjectURL(blob)
        const anchor  = document.createElement("a")
        anchor.href     = blobUrl
        anchor.download = `${alert.id}.mp4`
        document.body.appendChild(anchor)
        anchor.click()
        document.body.removeChild(anchor)
        setTimeout(() => URL.revokeObjectURL(blobUrl), 5_000)

        setExportState({ phase: "done" })
        addToast("Evidence clip downloaded successfully.", "success")
        setTimeout(() => setExportState({ phase: "idle" }), 4_000)
        return

      } catch (err) {
        const msg = err instanceof Error ? err.message : "Network error — is the API running?"
        setExportState({ phase: "error", message: msg })
        addToast(msg, "error")
        return
      }
    }
  }, [alert, exportState.phase, addToast])

  const handleExportReport = useCallback(async () => {
    if (!alert) return
    if (reportState.phase === "downloading") return

    setReportState({ phase: "downloading" })

    try {
      const res = await fetch(`${API_BASE}/download_report/${alert.id}`)

      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        const msg = body?.detail ?? `Server error ${res.status}`
        setReportState({ phase: "error", message: msg })
        addToast(`PDF export failed: ${msg}`, "error")
        return
      }

      const blob = await res.blob()
      const blobUrl = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = blobUrl
      anchor.download = `${alert.id}.pdf`
      document.body.appendChild(anchor)
      anchor.click()
      document.body.removeChild(anchor)
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5_000)

      setReportState({ phase: "done" })
      addToast("Forensic PDF report downloaded.", "success")
      setTimeout(() => setReportState({ phase: "idle" }), 4_000)
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Network error — is the API running?"
      setReportState({ phase: "error", message: msg })
      addToast(msg, "error")
    }
  }, [alert, reportState.phase, addToast])

  // ── Threshold slider logic ──────────────────────────────────────────────────

  const sendThreshold = useCallback(async (value: number) => {
    setThresholdBusy(true)
    try {
      const res = await fetch(`${API_BASE}/set_threshold`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ threshold: value / 100 }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        addToast(`Could not update threshold: ${body?.detail ?? res.status}`, "error")
      } else {
        addToast(`AI sensitivity set to ${value}%`, "success")
      }
    } catch {
      addToast("Cannot reach API — threshold not updated.", "error")
    } finally {
      setThresholdBusy(false)
    }
  }, [addToast])

  const handleThresholdChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = Number(e.target.value)
    setThreshold(value)
    if (debounceTimerRef.current !== null) clearTimeout(debounceTimerRef.current)
    debounceTimerRef.current = setTimeout(() => sendThreshold(value), THRESHOLD_DEBOUNCE_MS)
  }, [sendThreshold])

  // ── Cooldown slider logic (تمت استعادته بناءً على الطلب) ───────────────────────────

  const sendCooldown = useCallback(async (value: number) => {
    setCooldownBusy(true)
    try {
      const res = await fetch(`${API_BASE}/set_cooldown`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ cooldown: value }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        addToast(`Could not update timeout: ${body?.detail ?? res.status}`, "error")
      } else {
        addToast(`Alert timeout set to ${value}s`, "success")
      }
    } catch {
      addToast("Cannot reach API — timeout not updated.", "error")
    } finally {
      setCooldownBusy(false)
    }
  }, [addToast])

  const handleCooldownChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = Number(e.target.value)
    setCooldown(value)
    if (debounceCooldownRef.current !== null) clearTimeout(debounceCooldownRef.current)
    debounceCooldownRef.current = setTimeout(() => sendCooldown(value), THRESHOLD_DEBOUNCE_MS)
  }, [sendCooldown])

  const loadFacePolicy = useCallback(async () => {
    try {
      let policy: Record<string, unknown> = {}

      const policyRes = await fetch(`${API_BASE}/face/policy`)
      if (policyRes.ok) {
        const policyPayload = await policyRes.json()
        policy = (policyPayload?.policy ?? {}) as Record<string, unknown>
      } else {
        const statusRes = await fetch(`${API_BASE}/face/status`)
        if (!statusRes.ok) return
        const statusPayload = await statusRes.json()
        policy = (statusPayload?.policy ?? {}) as Record<string, unknown>
      }

      if (typeof policy.identityLabelingEnabled === "boolean") setFaceIdentityLabeling(policy.identityLabelingEnabled)
      if (typeof policy.recognitionAuditEnabled === "boolean") setFaceAuditEnabled(policy.recognitionAuditEnabled)
      if (typeof policy.recognitionAuditCooldownSec === "number") setFaceAuditCooldown(policy.recognitionAuditCooldownSec)
    } catch {
      // Keep local defaults when API is unreachable.
    }
  }, [])

  const sendFacePolicy = useCallback(async (body: Record<string, unknown>) => {
    const res = await fetch(`${API_BASE}/face/policy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const responseBody = await res.json().catch(() => ({}))
      throw new Error(responseBody?.detail ?? `Server error ${res.status}`)
    }
  }, [])

  const toggleIdentityLabeling = useCallback(async () => {
    const next = !faceIdentityLabeling
    setFaceIdentityLabeling(next)
    setFaceIdentityBusy(true)
    try {
      await sendFacePolicy({ identity_labeling_enabled: next })
      addToast(next ? "Identity labels enabled." : "Identity labels masked.", "success")
    } catch (err) {
      setFaceIdentityLabeling(!next)
      const msg = err instanceof Error ? err.message : "Failed to update identity policy."
      addToast(msg, "error")
    } finally {
      setFaceIdentityBusy(false)
    }
  }, [faceIdentityLabeling, sendFacePolicy, addToast])

  const toggleFaceAudit = useCallback(async () => {
    const next = !faceAuditEnabled
    setFaceAuditEnabled(next)
    setFaceAuditBusy(true)
    try {
      await sendFacePolicy({ recognition_audit_enabled: next })
      addToast(next ? "Face audit enabled." : "Face audit paused.", "success")
    } catch (err) {
      setFaceAuditEnabled(!next)
      const msg = err instanceof Error ? err.message : "Failed to update face audit policy."
      addToast(msg, "error")
    } finally {
      setFaceAuditBusy(false)
    }
  }, [faceAuditEnabled, sendFacePolicy, addToast])

  const sendFaceAuditCooldown = useCallback(async (value: number) => {
    setFaceAuditCooldownBusy(true)
    try {
      await sendFacePolicy({ recognition_audit_cooldown_sec: value })
      addToast(`Face audit cooldown set to ${value}s`, "success")
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to update face audit cooldown."
      addToast(msg, "error")
    } finally {
      setFaceAuditCooldownBusy(false)
    }
  }, [sendFacePolicy, addToast])

  const handleFaceAuditCooldownChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = Number(e.target.value)
    setFaceAuditCooldown(value)
    if (debounceFaceAuditCooldownRef.current !== null) clearTimeout(debounceFaceAuditCooldownRef.current)
    debounceFaceAuditCooldownRef.current = setTimeout(() => sendFaceAuditCooldown(value), THRESHOLD_DEBOUNCE_MS)
  }, [sendFaceAuditCooldown])

  useEffect(() => {
    void loadFacePolicy()
  }, [loadFacePolicy])

  useEffect(() => () => {
    if (debounceTimerRef.current !== null) clearTimeout(debounceTimerRef.current)
    if (debounceCooldownRef.current !== null) clearTimeout(debounceCooldownRef.current)
    if (debounceFaceAuditCooldownRef.current !== null) clearTimeout(debounceFaceAuditCooldownRef.current)
  }, [])

  // ── Render: no active incident ─────────────────────────────────────────────
  if (!alert) {
    return (
      <div className="relative flex h-full flex-col p-4">
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center border-2 border-dashed border-border rounded-xl bg-card/50">
          <ShieldCheck className="h-10 w-10 text-muted-foreground/30" />
          <div>
            <p className="text-sm font-medium text-muted-foreground">Selection Required</p>
            <p className="mt-1 text-xs text-muted-foreground/60">Select an alert from the feed to view controls.</p>
          </div>
        </div>
        
        {/* أشرطة التحكم تظل ظاهرة حتى بدون تحديد حادث لضبط الإعدادات العامة */}
        <div className="mt-4 space-y-3">
          <ThresholdSlider value={threshold} busy={thresholdBusy} onChange={handleThresholdChange} />
          <CooldownSlider value={cooldown} busy={cooldownBusy} onChange={handleCooldownChange} />
          <FacePolicyControls
            identityLabeling={faceIdentityLabeling}
            identityBusy={faceIdentityBusy}
            auditEnabled={faceAuditEnabled}
            auditBusy={faceAuditBusy}
            auditCooldown={faceAuditCooldown}
            auditCooldownBusy={faceAuditCooldownBusy}
            onToggleIdentity={toggleIdentityLabeling}
            onToggleAudit={toggleFaceAudit}
            onChangeAuditCooldown={handleFaceAuditCooldownChange}
          />
        </div>
        
        <ToastStack toasts={toasts} onDismiss={dismissToast} />
      </div>
    )
  }

  // ── Render: active incident ────────────────────────────────────────────────
  const faceSummary = alert.faceSummary
  const recognizedPeople = faceSummary?.recognized ?? []
  const unknownIds = faceSummary?.unknownIds ?? []
  const unknownDetails = faceSummary?.unknownDetails ?? []
  const knownCount = faceSummary?.recognizedCount ?? recognizedPeople.length
  const unknownCount = faceSummary?.unknownCount ?? unknownIds.length
  const totalFaces = faceSummary?.totalFaces ?? knownCount + unknownCount

  return (
    <div className="relative flex h-full flex-col gap-4 p-4">

      {/* الهيدر */}
      <div className="flex items-center gap-2 pb-1 border-b border-border">
        <ShieldAlert className="h-5 w-5 text-primary" />
        <h2 className="text-sm font-bold tracking-tight">Incident Control Panel</h2>
      </div>

      {/* ── Incident Details ──────────────────────────────────────────── */}
      <div className="rounded-xl border border-border bg-card shadow-inner">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5 bg-muted/20">
          <Crosshair className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">Core Metrics</span>
          <Badge
            className={cn(
              "ml-auto h-5 border px-1.5 font-mono text-[9px] uppercase",
              alert.severity === "critical" ? "border-danger/30 bg-danger/20 text-danger"
              : alert.severity === "high" ? "border-warning/30 bg-warning/20 text-warning"
              : "border-primary/30 bg-primary/20 text-primary"
            )}
          >
            {alert.severity} Severity
          </Badge>
        </div>
        <div className="flex flex-col gap-3 p-4">
          <MetadataRow icon={<Camera className="h-3.5 w-3.5" />} label="Source Camera" value={`${alert.cameraId} — ${alert.location}`} />
          <MetadataRow icon={<Clock className="h-3.5 w-3.5" />}  label="Event Timestamp" value={alert.timestamp} />
          <MetadataRow icon={<Crosshair className="h-3.5 w-3.5" />} label="Classification" value="Active Violence" />

          {/* Confidence bar */}
          <div className="mt-1 rounded-lg bg-secondary/50 p-3 border border-border/50">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Model Confidence</span>
              <span className="font-mono text-xs font-bold text-danger">{alert.confidence.toFixed(1)}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  alert.severity === "critical" ? "bg-danger"
                  : alert.severity === "high"   ? "bg-warning"
                  : "bg-primary"
                )}
                style={{ width: `${alert.confidence}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── Floor plan / Camera Location (ديناميكي بناءً على الكاميرا) ───────────────── */}
      <div className="rounded-xl border border-border bg-card shadow-inner">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5 bg-muted/20">
          <ScanFace className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">Face Intelligence</span>
          <Badge variant="outline" className={cn("h-5 border font-mono text-[9px]", faceSummary?.identityLabelingEnabled === false ? "border-warning/30 bg-warning/10 text-warning" : "border-success/30 bg-success/10 text-success")}>
            {faceSummary?.identityLabelingEnabled === false ? "MASKED" : "IDENTITY ON"}
          </Badge>
          <Badge variant="outline" className="ml-auto h-5 border-primary/30 bg-primary/10 font-mono text-[9px] text-primary">
            {faceSummary?.enabled ? "ACTIVE" : "OFF"}
          </Badge>
        </div>

        <div className="flex flex-col gap-3 p-4">
          <div className="grid grid-cols-3 gap-2">
            <FaceMetric label="Total" value={String(totalFaces)} tone="text-foreground" />
            <FaceMetric label="Known" value={String(knownCount)} tone="text-success" />
            <FaceMetric label="Unknown" value={String(unknownCount)} tone="text-warning" />
          </div>

          {recognizedPeople.length > 0 && (
            <div className="rounded-lg border border-success/20 bg-success/5 p-2.5">
              <p className="mb-1.5 text-[10px] uppercase tracking-wider text-success/80 font-semibold">Recognized People</p>
              <div className="flex flex-wrap gap-1.5">
                {recognizedPeople.slice(0, 8).map((person, idx) => {
                  const label = person?.label ?? person?.personId ?? `Known-${idx + 1}`
                  return (
                    <span key={`${label}-${idx}`} className="inline-flex items-center gap-1 rounded border border-success/30 bg-success/10 px-2 py-0.5 font-mono text-[10px] text-success">
                      <UserRound className="h-3 w-3" />
                      {label}
                    </span>
                  )
                })}
              </div>
            </div>
          )}

          {unknownIds.length > 0 && (
            <div className="rounded-lg border border-warning/20 bg-warning/5 p-2.5">
              <p className="mb-1.5 text-[10px] uppercase tracking-wider text-warning/90 font-semibold">Unknown IDs</p>
              <div className="flex flex-wrap gap-1.5">
                {unknownIds.slice(0, 12).map((id) => (
                  <span key={id} className="rounded border border-warning/30 bg-warning/10 px-2 py-0.5 font-mono text-[10px] text-warning">
                    {id}
                  </span>
                ))}
              </div>
            </div>
          )}

          {unknownDetails.length > 0 && (
            <div className="rounded-lg border border-border/70 bg-background/60 p-2.5">
              <p className="mb-1.5 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Unknown Timeline</p>
              <div className="max-h-24 space-y-1 overflow-y-auto custom-scrollbar pr-1">
                {unknownDetails.slice(0, 12).map((item) => (
                  <div key={`${item.id}-${item.lastSeenFrame}`} className="flex items-center justify-between rounded border border-border/60 bg-card px-2 py-1">
                    <span className="font-mono text-[10px] text-foreground">{item.id}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">frames: {item.durationFrames}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">hits: {item.hitStreak}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5 bg-muted/20">
          <MapPin className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">Spatial Location</span>
        </div>
        <div className="p-4 flex justify-center bg-background/50">
          <svg viewBox="0 0 100 70" className="w-full max-w-[240px]" aria-label="Floor plan">
            <rect x="5" y="5" width="90" height="60" rx="2" fill="none" stroke="#334155" strokeWidth="0.5" />
            {[
              { x: 5,  y: 5,  w: 30, h: 30, label: "Entrance" },
              { x: 35, y: 5,  w: 30, h: 30, label: "Hallway" },
              { x: 65, y: 5,  w: 30, h: 30, label: "Lobby" },
              { x: 5,  y: 35, w: 45, h: 30, label: "Office A" },
              { x: 50, y: 35, w: 45, h: 30, label: "Office B" },
            ].map((r) => (
              <g key={r.label}>
                <rect x={r.x} y={r.y} width={r.w} height={r.h} rx="1" fill="rgba(30,41,59,0.5)" stroke="#334155" strokeWidth="0.3" />
                <text x={r.x + r.w / 2} y={r.y + r.h / 2 + 1} textAnchor="middle" fontSize="3" fontFamily="monospace" fill="#64748b">{r.label}</text>
              </g>
            ))}
            
            {/* Dynamic Camera Location Logic */}
            {(() => {
              const getCameraCoords = (camId: string) => {
                switch (camId) {
                  case "CAM-01": return { cx: 20, cy: 20 }
                  case "CAM-02": return { cx: 50, cy: 20 }
                  case "CAM-03": return { cx: 80, cy: 20 }
                  default:       return { cx: 20, cy: 20 }
                }
              }
              const coords = getCameraCoords(alert.cameraId)
              
              return (
                <>
                  <circle cx={coords.cx} cy={coords.cy} r="6" fill="rgba(239,68,68,0.2)">
                    <animate attributeName="r"       values="4;8;4"     dur="1.5s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.6;0.1;0.6" dur="1.5s" repeatCount="indefinite" />
                  </circle>
                  <circle cx={coords.cx} cy={coords.cy} r="2.5" fill="#ef4444" stroke="#0f172a" strokeWidth="0.5" />
                  <text x={coords.cx} y={coords.cy - 7} textAnchor="middle" fontSize="3" fontFamily="monospace" fontWeight="bold" fill="#ef4444">{alert.cameraId}</text>
                </>
              )
            })()}
          </svg>
        </div>
      </div>

      {/* فاصل مرن للدفع للأسفل */}
      <div className="flex-1"></div>

      {/* ── Settings Sliders (تم تجميعها في الأسفل) ────────────────────── */}
      <div className="flex flex-col gap-3 pt-3 border-t border-border">
        <ThresholdSlider value={threshold} busy={thresholdBusy} onChange={handleThresholdChange} />
        <CooldownSlider value={cooldown} busy={cooldownBusy} onChange={handleCooldownChange} />
        <FacePolicyControls
          identityLabeling={faceIdentityLabeling}
          identityBusy={faceIdentityBusy}
          auditEnabled={faceAuditEnabled}
          auditBusy={faceAuditBusy}
          auditCooldown={faceAuditCooldown}
          auditCooldownBusy={faceAuditCooldownBusy}
          onToggleIdentity={toggleIdentityLabeling}
          onToggleAudit={toggleFaceAudit}
          onChangeAuditCooldown={handleFaceAuditCooldownChange}
        />
      </div>

      {/* ── Action buttons ────────────────────────────────────────────── */}
      <div className="flex flex-col gap-2.5 mt-1">
        <Button onClick={handleDispatch} className="h-12 w-full gap-2.5 bg-danger font-bold text-sm text-danger-foreground shadow-lg shadow-danger/20 transition-all hover:bg-danger/90 active:scale-[0.98]">
          <ShieldAlert className="h-4.5 w-4.5" />
          INITIATE EMERGENCY DISPATCH
          <ChevronRight className="ml-auto h-4 w-4" />
        </Button>

        <div className="flex gap-2.5">
          <Button variant="secondary" onClick={handleFalseAlarm} className="h-10 flex-1 gap-1.5 bg-secondary text-xs text-secondary-foreground transition-all hover:bg-secondary/80 active:scale-[0.97]">
            <XCircle className="h-3.5 w-3.5" /> Mark False Alarm
          </Button>

          <Button variant="outline" onClick={handleExportEvidence} disabled={exportState.phase === "polling" || exportState.phase === "downloading"} className={cn("h-10 flex-1 gap-1.5 border-border text-xs transition-all active:scale-[0.97]", exportState.phase === "done" ? "border-success/40 bg-success/10 text-success hover:bg-success/20" : exportState.phase === "error" ? "border-danger/40 bg-danger/10 text-danger hover:bg-danger/20" : "text-foreground hover:bg-secondary")}>
            <ExportButtonContent state={exportState} />
          </Button>
        </div>

        <Button
          variant="outline"
          onClick={handleExportReport}
          disabled={reportState.phase === "downloading"}
          className={cn(
            "h-10 w-full gap-1.5 border-border text-xs transition-all active:scale-[0.97]",
            reportState.phase === "done"
              ? "border-primary/40 bg-primary/10 text-primary hover:bg-primary/20"
              : reportState.phase === "error"
                ? "border-danger/40 bg-danger/10 text-danger hover:bg-danger/20"
                : "text-foreground hover:bg-secondary"
          )}
        >
          {reportState.phase === "idle" && <>
            <FileDown className="h-3.5 w-3.5" />
            Export PDF Report
          </>}
          {reportState.phase === "downloading" && <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Generating PDF...
          </>}
          {reportState.phase === "done" && <>
            <CheckCircle2 className="h-3.5 w-3.5" />
            PDF Ready
          </>}
          {reportState.phase === "error" && <>
            <AlertCircle className="h-3.5 w-3.5" />
            PDF Failed
          </>}
        </Button>
      </div>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}

// ─── Threshold slider ─────────────────────────────────────────────────────────

function ThresholdSlider({ value, busy, onChange }: { value: number; busy: boolean; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void }) {
  const trackColor = value < 40 ? "#22c55e" : value < 65 ? "#f59e0b" : "#ef4444"
  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-sm">
      <div className="mb-2.5 flex items-center gap-2">
        <SlidersHorizontal className="h-3.5 w-3.5 text-primary" />
        <span className="text-xs font-semibold text-foreground">AI Detection Sensitivity</span>
        {busy ? <Loader2 className="ml-auto h-3 w-3 animate-spin text-muted-foreground" /> : <span className="ml-auto font-mono text-[11px] font-bold" style={{ color: trackColor }}>{value}%</span>}
      </div>
      <input type="range" min={10} max={95} step={1} value={value} onChange={onChange} aria-label="Detection threshold" className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-secondary outline-none" style={{ background: `linear-gradient(to right,${trackColor} 0%,${trackColor} ${((value - 10) / 85) * 100}%,rgb(30 41 59) ${((value - 10) / 85) * 100}%,rgb(30 41 59) 100%)` }} />
      <div className="mt-1 flex justify-between">
        <span className="text-[9px] text-muted-foreground font-medium">Responsive (10%)</span><span className="text-[9px] text-muted-foreground font-medium">Strict (95%)</span>
      </div>
    </div>
  )
}

// ─── Cooldown slider (تمت استعادته بناءً على الطلب) ─────────────────────────────────

function CooldownSlider({ value, busy, onChange }: { value: number; busy: boolean; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-sm">
      <div className="mb-2.5 flex items-center gap-2">
        <Timer className="h-3.5 w-3.5 text-blue-500" />
        <span className="text-xs font-semibold text-foreground">Alert Suppress Timeout</span>
        {busy ? <Loader2 className="ml-auto h-3 w-3 animate-spin text-muted-foreground" /> : <span className="ml-auto font-mono text-[11px] font-bold text-blue-500">{value}s</span>}
      </div>
      <input type="range" min={15} max={120} step={5} value={value} onChange={onChange} aria-label="Alert Timeout" className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-secondary outline-none" style={{ background: `linear-gradient(to right,#3b82f6 0%,#3b82f6 ${((value - 15) / 105) * 100}%,rgb(30 41 59) ${((value - 15) / 105) * 100}%,rgb(30 41 59) 100%)` }} />
      <div className="mt-1 flex justify-between">
        <span className="text-[9px] text-muted-foreground font-medium">Instant (15s)</span><span className="text-[9px] text-muted-foreground font-medium">Delayed (120s)</span>
      </div>
    </div>
  )
}

// ─── Toast stack ─────────────────────────────────────────────────────────────

function FacePolicyControls({
  identityLabeling,
  identityBusy,
  auditEnabled,
  auditBusy,
  auditCooldown,
  auditCooldownBusy,
  onToggleIdentity,
  onToggleAudit,
  onChangeAuditCooldown,
}: {
  identityLabeling: boolean
  identityBusy: boolean
  auditEnabled: boolean
  auditBusy: boolean
  auditCooldown: number
  auditCooldownBusy: boolean
  onToggleIdentity: () => void
  onToggleAudit: () => void
  onChangeAuditCooldown: (e: React.ChangeEvent<HTMLInputElement>) => void
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-3.5 shadow-sm">
      <div className="mb-2.5 flex items-center gap-2">
        <ScanFace className="h-3.5 w-3.5 text-primary" />
        <span className="text-xs font-semibold text-foreground">Face Policy Controls</span>
      </div>

      <div className="space-y-2.5">
        <div className="flex items-center justify-between rounded-lg border border-border/60 bg-background/60 px-2.5 py-2">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Identity Labels</p>
            <p className="text-[11px] text-foreground/90">Show real known names in alerts.</p>
          </div>
          <Button size="sm" variant="outline" onClick={onToggleIdentity} disabled={identityBusy} className={cn("h-7 min-w-[96px] text-[10px] font-semibold", identityLabeling ? "border-success/30 bg-success/10 text-success hover:bg-success/20" : "border-warning/30 bg-warning/10 text-warning hover:bg-warning/20")}>
            {identityBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : identityLabeling ? "ON" : "MASKED"}
          </Button>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border/60 bg-background/60 px-2.5 py-2">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Recognition Audit</p>
            <p className="text-[11px] text-foreground/90">Write known/unknown sightings to audit log.</p>
          </div>
          <Button size="sm" variant="outline" onClick={onToggleAudit} disabled={auditBusy} className={cn("h-7 min-w-[96px] text-[10px] font-semibold", auditEnabled ? "border-primary/30 bg-primary/10 text-primary hover:bg-primary/20" : "border-border bg-secondary/30 text-muted-foreground hover:bg-secondary")}>
            {auditBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : auditEnabled ? "ENABLED" : "PAUSED"}
          </Button>
        </div>

        <div className="rounded-lg border border-border/60 bg-background/60 px-2.5 py-2">
          <div className="mb-2 flex items-center gap-2">
            <Timer className="h-3.5 w-3.5 text-primary" />
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">Audit Cooldown</p>
            {auditCooldownBusy ? <Loader2 className="ml-auto h-3 w-3 animate-spin text-muted-foreground" /> : <span className="ml-auto font-mono text-[11px] font-bold text-primary">{auditCooldown}s</span>}
          </div>
          <input
            type="range"
            min={5}
            max={120}
            step={5}
            value={auditCooldown}
            onChange={onChangeAuditCooldown}
            aria-label="Face audit cooldown"
            className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-secondary outline-none"
            style={{ background: `linear-gradient(to right,#22c55e 0%,#22c55e ${((auditCooldown - 5) / 115) * 100}%,rgb(30 41 59) ${((auditCooldown - 5) / 115) * 100}%,rgb(30 41 59) 100%)` }}
          />
        </div>
      </div>
    </div>
  )
}

function ToastStack({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  if (toasts.length === 0) return null
  return (
    <div className="sticky bottom-0 left-0 right-0 z-50 flex flex-col gap-2 pb-2 pt-3">
      {toasts.map((t) => {
        const styles: Record<ToastVariant, string> = { success: "border-success/30 bg-success/10 text-success shadow-success/10", info: "border-primary/30 bg-primary/10 text-primary shadow-primary/10", error: "border-danger/30 bg-danger/10 text-danger shadow-danger/10" }
        const Icon = t.variant === "success" ? CheckCheck : t.variant === "error" ? AlertCircle : Info
        return (
          <div key={t.id} className={cn("flex items-start gap-2.5 rounded-xl border px-4 py-3 text-[11px] shadow-lg", styles[t.variant])}>
            <Icon className="mt-0.5 h-4 w-4 flex-shrink-0" /><span className="flex-1 leading-relaxed font-medium">{t.message}</span>
            <button onClick={() => onDismiss(t.id)} className="mt-0.5 opacity-60 transition-opacity hover:opacity-100" aria-label="Dismiss"><X className="h-3.5 w-3.5" /></button>
          </div>
        )
      })}
    </div>
  )
}

// ─── Export button label ──────────────────────────────────────────────────────

function ExportButtonContent({ state: s }: { state: ExportPhase }) {
  switch (s.phase) {
    case "idle":        return <><Download className="h-3.5 w-3.5" />Export Clip</>
    case "polling":     return <><Loader2 className="h-3.5 w-3.5 animate-spin" />Compiling… ({s.attempt})</>
    case "downloading": return <><Loader2 className="h-3.5 w-3.5 animate-spin" />Downloading…</>
    case "done":        return <><CheckCircle2 className="h-3.5 w-3.5" />Saved</>
    case "error":       return <><AlertCircle className="h-3.5 w-3.5" />Failed</>
  }
}

// ─── MetadataRow ──────────────────────────────────────────────────────────────

function MetadataRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="mt-1 text-muted-foreground/80">{icon}</span>
      <div className="flex flex-col">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</span>
        <span className="text-xs font-semibold text-foreground leading-snug">{value}</span>
      </div>
    </div>
  )
}

// ─── Utility ──────────────────────────────────────────────────────────────────

function FaceMetric({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/60 px-2 py-1.5 text-center">
      <p className="text-[9px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className={cn("font-mono text-xs font-bold", tone)}>{value}</p>
    </div>
  )
}

const _sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
