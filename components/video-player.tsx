"use client"

import { useState, useEffect, useRef, useCallback, memo } from "react"
import {
  Repeat, Timer, Radio, Play, Pause, Maximize2,
  WifiOff, Loader2, Camera,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export interface LiveAlert {
  id:         string
  timestamp:  string
  isoTime:    string
  confidence: number
  type:       "Violence"
  severity:   "critical" | "high" | "medium"
  cameraId:   string
  location:   string
}

interface VideoPlayerProps {
  activeAlert: LiveAlert | null
  privacyMode: boolean
}

const API_BASE        = "http://localhost:8000"
const VIDEO_FEED_URL  = `${API_BASE}/video_feed`
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

  const confidence = visibleAlert?.confidence ?? 0
  const cameraId   = visibleAlert?.cameraId   ?? activeCamId
  const timestamp  = visibleAlert?.timestamp  ?? "--:--:-- UTC"

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
          <><span className="flex h-2.5 w-2.5 bg-danger rounded-full animate-ping"/><span className="text-sm font-bold text-danger">⚠ VIOLENCE DETECTED — CONFIDENCE {confidence.toFixed(1)}%</span></>
        ) : (
          <><span className="flex h-2.5 w-2.5 bg-success rounded-full animate-pulse"/><span className="text-sm font-semibold text-success">MONITORING — No Threat Detected</span><span className="ml-auto font-mono text-[10px] text-muted-foreground">{activeCamId} — Live Feed</span></>
        )}
      </div>

      {/* ── Video Area ── */}
      <div className="relative flex-1 overflow-hidden bg-black">
        {privacyMode && <div className="absolute inset-0 z-30 flex items-center justify-center backdrop-blur-2xl"><span className="border border-danger/40 bg-black/60 px-4 py-1.5 font-mono text-sm text-danger">PRIVACY MODE — FEED REDACTED</span></div>}
        {isSwitching && <div className="absolute inset-0 z-25 flex flex-col items-center justify-center gap-3 bg-black/70 backdrop-blur-sm"><Loader2 className="h-8 w-8 animate-spin text-primary" /><p className="font-mono text-sm font-semibold text-primary">Connecting to {activeCamId}…</p></div>}
        {streamError && !isSwitching && <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-background/90"><WifiOff className="h-10 w-10 text-muted-foreground/50" /><Button size="sm" onClick={() => { setStreamError(false); setStreamKey((k) => k + 1) }}>Retry</Button></div>}
        
        {!streamError && <img key={streamKey} src={streamSrc} className="h-full w-full object-cover" onError={() => setStreamError(true)} />}

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
        <div className="pointer-events-none absolute right-3 top-3 z-20 flex items-center gap-1.5"><span className={cn("h-2 w-2 rounded-full", showViolence ? "animate-ping bg-danger" : "animate-pulse bg-danger")} /><span className="font-mono text-[10px] font-bold text-danger">REC</span></div>
        <div className="pointer-events-none absolute bottom-10 left-3 z-20 flex items-center gap-2"><span className="font-mono text-[10px] text-white/60">{timestamp}</span><span className="text-[10px] text-white/30">|</span><span className="font-mono text-[10px] text-primary">{cameraId}</span></div>
      </div>

      {/* ── Controls Bar ── */}
      <div className="flex items-center justify-between border-t border-border bg-card px-4 py-2">
        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setIsPlaying((p) => !p)}>{isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}</Button>
      </div>
    </div>
  )
})
