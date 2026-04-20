"use client"

import { useState, useEffect, useRef, useCallback, useMemo, memo } from "react"
import {
  Repeat, Timer, Radio, Play, Pause, Maximize2,
  WifiOff, Loader2, Camera,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export interface FaceObservation {
  id: string
  label: string
  kind: "known" | "unknown"
  confidence: number
  bbox: number[]
}

export interface FaceUnknownDetail {
  id: string
  firstSeenFrame: number
  lastSeenFrame: number
  durationFrames: number
  firstSeenAt: string
  lastSeenAt: string
  hitStreak: number
  lastBbox: number[]
}

export interface FaceSummaryPayload {
  enabled: boolean
  identityLabelingEnabled?: boolean
  frameIndex?: number
  totalFaces: number
  recognized: Array<{ personId?: string; label?: string; confidence?: number; distance?: number }>
  recognizedCount?: number
  unknownIds: string[]
  unknownCount: number
  unknownDetails?: FaceUnknownDetail[]
  observations?: FaceObservation[]
}

export interface LiveAlert {
  id:         string
  timestamp:  string
  isoTime:    string
  confidence: number
  modelConfidence?: number
  rawModelConfidence?: number
  threatConfidence?: number
  type:       "Violence"
  severity:   "critical" | "high" | "medium"
  cameraId:   string
  location:   string
  fusionScore?: number
  fusionModel?: string
  motionScore?: number
  weaponScore?: number
  weaponLabels?: string[]
  weaponDetectorReady?: boolean
  fusionReason?: string
  faceSummary?: FaceSummaryPayload
}

interface VideoPlayerProps {
  activeAlert: LiveAlert | null
  privacyMode: boolean
}

const API_BASE        = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const VIDEO_FEED_URL  = `${API_BASE}/video_feed`
const LIVE_DEMO_URL   = process.env.NEXT_PUBLIC_LIVE_DEMO_URL ?? ""
const OVERLAY_LINGER_MS = 8_000
const SWITCH_SETTLE_MS = 900

const CAMERAS = [
  { id: "CAM-01", label: "CAM-01" },
  { id: "CAM-02", label: "CAM-02" },
  { id: "CAM-03", label: "CAM-03" },
] as const

type CameraId = (typeof CAMERAS)[number]["id"]

export const VideoPlayer = memo(function VideoPlayer({ activeAlert, privacyMode }: VideoPlayerProps) {
  const [isPlaying,     setIsPlaying]     = useState(true)
  const [activeControl, setActiveControl] = useState<string | null>(null)
  const [streamError,   setStreamError]   = useState(false)
  const [streamKey,     setStreamKey]     = useState(0)

  const [activeCamId,  setActiveCamId]  = useState<CameraId>("CAM-01")
  const [isSwitching,  setIsSwitching]  = useState(false)
  const [switchError,  setSwitchError]  = useState<string | null>(null)

  const [showViolence, setShowViolence] = useState(false)
  const [visibleAlert, setVisibleAlert] = useState<LiveAlert | null>(null)
  const lingerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (activeAlert === null) return
    if (activeAlert.cameraId !== activeCamId) return 

    setShowViolence(true)
    setVisibleAlert(activeAlert)

    if (lingerTimerRef.current !== null) clearTimeout(lingerTimerRef.current)
    lingerTimerRef.current = setTimeout(() => setShowViolence(false), OVERLAY_LINGER_MS)

    return () => {
      if (lingerTimerRef.current !== null) clearTimeout(lingerTimerRef.current)
    }
  }, [activeAlert?.id, activeCamId])

  const threatConfidence = visibleAlert?.threatConfidence ?? visibleAlert?.confidence ?? 0
  const modelConfidence = visibleAlert?.modelConfidence ?? visibleAlert?.confidence ?? 0
  const cameraId   = visibleAlert?.cameraId   ?? activeCamId
  const timestamp  = visibleAlert?.timestamp  ?? "--:--:-- UTC"
  const faceSummary = visibleAlert?.faceSummary ?? null

  const faceKnownLabels = useMemo(() => {
    if (!faceSummary?.recognized) return []
    const labels = faceSummary.recognized
      .map((item) => (item?.label ?? item?.personId ?? "").trim())
      .filter(Boolean)
    return Array.from(new Set(labels))
  }, [faceSummary])

  const faceUnknownIds = useMemo(() => {
    if (!faceSummary?.unknownIds) return []
    return Array.from(new Set(faceSummary.unknownIds.map((id) => id.trim()).filter(Boolean)))
  }, [faceSummary])

  const faceKnownCount = faceSummary?.recognizedCount ?? faceKnownLabels.length
  const faceUnknownCount = faceSummary?.unknownCount ?? faceUnknownIds.length
  const hasFaceIntelData = Boolean(faceSummary?.enabled && (faceSummary.totalFaces > 0 || faceKnownCount > 0 || faceUnknownCount > 0))

  const handleCameraSwitch = useCallback(async (camId: CameraId) => {
    if (camId === activeCamId || isSwitching) return
    setIsSwitching(true)
    setSwitchError(null)

    try {
      const res = await fetch(`${API_BASE}/switch_camera`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ camera_id: camId }),
      })

      if (!res.ok) throw new Error(`Server returned ${res.status}`)

      await new Promise<void>((r) => setTimeout(r, SWITCH_SETTLE_MS))
      setActiveCamId(camId)
      setStreamError(false)
      setStreamKey((k) => k + 1)
    } catch (err) {
      setSwitchError("Camera switch failed")
      setTimeout(() => setSwitchError(null), 4_000)
    } finally {
      setIsSwitching(false)
    }
  }, [activeCamId, isSwitching])

  const streamSrc = isPlaying ? `${VIDEO_FEED_URL}?k=${streamKey}` : undefined
  const isLiveDemoMode = LIVE_DEMO_URL.trim().length > 0

  return (
    <div className="flex h-full flex-col">
      {/* ── Camera Selector Bar ── */}
      <div className="flex items-center gap-1.5 border-b border-border bg-card/80 px-3 py-1.5">
        <Camera className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
        <span className="mr-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Camera</span>
        {CAMERAS.map((cam) => {
          const isActive = activeCamId === cam.id
          return (
            <button
              key={cam.id} onClick={() => handleCameraSwitch(cam.id)} disabled={isSwitching}
              className={cn(
                "flex items-center gap-1.5 rounded border px-2.5 py-0.5 font-mono text-[11px] font-semibold transition-all duration-200",
                isActive ? "border-primary/50 bg-primary/15 text-primary" : "border-transparent text-muted-foreground hover:border-border hover:bg-secondary hover:text-foreground"
              )}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", isActive ? "bg-primary animate-pulse" : "bg-muted-foreground/30")} />
              {cam.label}
            </button>
          )
        })}
        {isSwitching && <span className="ml-auto flex items-center gap-1.5 font-mono text-[10px] text-primary"><Loader2 className="h-3 w-3 animate-spin" />Connecting…</span>}
        {switchError && !isSwitching && <span className="ml-auto font-mono text-[10px] text-danger">✗ {switchError}</span>}
      </div>

      {/* ── Status Banner ── */}
      <div className={cn("flex items-center gap-2 border-b px-4 py-2 transition-all duration-700", showViolence ? "border-danger/40 bg-danger/10" : "border-border bg-card/60")}>
        {showViolence ? (
          <><span className="flex h-2.5 w-2.5 bg-danger rounded-full animate-ping"/><span className="text-sm font-bold text-danger">⚠ VIOLENCE DETECTED — THREAT {threatConfidence.toFixed(1)}% | MODEL {modelConfidence.toFixed(1)}%</span></>
        ) : (
          <><span className="flex h-2.5 w-2.5 bg-success rounded-full animate-pulse"/><span className="text-sm font-semibold text-success">MONITORING — No Threat Detected</span><span className="ml-auto font-mono text-[10px] text-muted-foreground">{activeCamId} — Live Feed</span></>
        )}
      </div>

      {/* ── Video Area ── */}
      <div className="relative flex-1 overflow-hidden bg-black">
        {privacyMode && <div className="absolute inset-0 z-30 flex items-center justify-center backdrop-blur-2xl"><span className="border border-danger/40 bg-black/60 px-4 py-1.5 font-mono text-sm text-danger">PRIVACY MODE — FEED REDACTED</span></div>}
        {isSwitching && <div className="absolute inset-0 z-25 flex flex-col items-center justify-center gap-3 bg-black/70 backdrop-blur-sm"><Loader2 className="h-8 w-8 animate-spin text-primary" /><p className="font-mono text-sm font-semibold text-primary">Connecting to {activeCamId}…</p></div>}
        {streamError && !isSwitching && <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-background/90"><WifiOff className="h-10 w-10 text-muted-foreground/50" /><Button size="sm" onClick={() => { setStreamError(false); setStreamKey((k) => k + 1) }}>Retry</Button></div>}
        
        {!streamError && !isLiveDemoMode && <img key={streamKey} src={streamSrc} className="h-full w-full object-cover" onError={() => setStreamError(true)} />}

        {isLiveDemoMode && (
          <iframe
            title="Live camera demo"
            src={LIVE_DEMO_URL}
            className="h-full w-full border-0"
            allow="autoplay; fullscreen; picture-in-picture"
            referrerPolicy="no-referrer"
          />
        )}

        {showViolence && <div className="pointer-events-none absolute inset-0 z-10 border-[3px] border-danger animate-[pulse_1.2s_ease-in-out_infinite]" style={{ boxShadow: "inset 0 0 40px rgba(239,68,68,0.25)" }} />}
        <div className={cn("pointer-events-none absolute inset-0 z-10 transition-opacity duration-700", showViolence ? "opacity-60" : "opacity-20")} style={{ background: "repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.08) 2px,rgba(0,0,0,0.08) 4px)" }} />
        
        {showViolence && (
          <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center pt-6">
            <div className="flex items-center gap-3 rounded-lg border border-danger/50 bg-black/70 px-6 py-3 backdrop-blur-sm">
              <span className="font-mono text-base font-black uppercase text-danger drop-shadow-lg">⚠ VIOLENCE DETECTED</span>
            </div>
          </div>
        )}

        {showViolence && visibleAlert && <div className="pointer-events-none absolute left-3 top-3 z-20"><Badge className="h-5 border-danger/40 bg-danger/20 text-danger">{visibleAlert.severity}</Badge></div>}
        {isLiveDemoMode && <div className="pointer-events-none absolute left-3 top-3 z-20"><Badge className="h-5 border-primary/40 bg-primary/20 text-primary">LIVE DEMO</Badge></div>}
        <div className="pointer-events-none absolute right-3 top-3 z-20 flex items-center gap-1.5"><span className={cn("h-2 w-2 rounded-full", showViolence ? "animate-ping bg-danger" : "animate-pulse bg-danger")} /><span className="font-mono text-[10px] font-bold text-danger">REC</span></div>
        {showViolence && hasFaceIntelData && (
          <div className="pointer-events-none absolute bottom-14 left-3 z-20 max-w-[80%] rounded-md border border-primary/30 bg-black/70 px-2.5 py-2 backdrop-blur-sm">
            <div className="mb-1 flex items-center gap-1.5">
              <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-primary">Face Intel</span>
              <span className="text-[10px] text-white/40">|</span>
              <span className="font-mono text-[10px] text-white/70">Known: {faceKnownCount}</span>
              <span className="font-mono text-[10px] text-white/70">Unknown: {faceUnknownCount}</span>
            </div>
            {faceKnownLabels.length > 0 && (
              <div className="mb-1 flex flex-wrap gap-1">
                {faceKnownLabels.slice(0, 4).map((label) => (
                  <span key={label} className="rounded border border-success/30 bg-success/15 px-1.5 py-0.5 font-mono text-[10px] text-success">
                    {label}
                  </span>
                ))}
              </div>
            )}
            {faceUnknownIds.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {faceUnknownIds.slice(0, 6).map((id) => (
                  <span key={id} className="rounded border border-warning/30 bg-warning/15 px-1.5 py-0.5 font-mono text-[10px] text-warning">
                    {id}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="pointer-events-none absolute bottom-10 left-3 z-20 flex items-center gap-2"><span className="font-mono text-[10px] text-white/60">{timestamp}</span><span className="text-[10px] text-white/30">|</span><span className="font-mono text-[10px] text-primary">{cameraId}</span></div>
      </div>

      {/* ── Controls Bar ── */}
      <div className="flex items-center justify-between border-t border-border bg-card px-4 py-2">
        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setIsPlaying((p) => !p)}>{isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}</Button>
      </div>
    </div>
  )
})
