"use client"

import { useState, useEffect, useRef, useMemo, memo } from "react"
import {
  Repeat, Timer, Radio, Play, Pause, Maximize2,
  WifiOff, Loader2, Camera,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { DetectionCategory, CategoryScore } from "@/lib/detection-types"

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
  clipUrl?: string
  categories?: CategoryScore[]
  primaryCategory?: DetectionCategory
  allCategories?: DetectionCategory[]
  threatType?: "violence" | "weapon"
  alertLatencyMs?: number
}

interface VideoPlayerProps {
  cameraId: CameraId
  activeAlert: LiveAlert | null
  privacyMode: boolean
}

const API_BASE          = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const LIVE_DEMO_URL     = process.env.NEXT_PUBLIC_LIVE_DEMO_URL ?? ""
const OVERLAY_LINGER_MS = 8_000
const DEMO_LOADING_MS   = 4_000

const CAMERAS = [
  { id: "CAM-01",     label: "CAM-01",       isLive: true,  isDemo: false },
  { id: "CAM-02",     label: "CAM-02",       isLive: true,  isDemo: false },
  { id: "EXAMPLE-01", label: "Fight Clip 1", isLive: false, isDemo: true  },
  { id: "EXAMPLE-02", label: "Fight Clip 2", isLive: false, isDemo: true  },
] as const

type CameraId = (typeof CAMERAS)[number]["id"]

export const VideoPlayer = memo(function VideoPlayer({ cameraId: propCameraId, activeAlert, privacyMode }: VideoPlayerProps) {
  const [isPlaying,     setIsPlaying]     = useState(true)
  const [activeControl, setActiveControl] = useState<string | null>(null)
  const [streamError,   setStreamError]   = useState(false)
  const [streamKey,     setStreamKey]     = useState(0)
  const [demoLoading,   setDemoLoading]   = useState(false)
  const [demoStreamError, setDemoStreamError] = useState(false)
  const demoLoadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isDemo = CAMERAS.find(c => c.id === propCameraId)?.isDemo ?? false



  const [showViolence, setShowViolence] = useState(false)
  const [visibleAlert, setVisibleAlert] = useState<LiveAlert | null>(null)
  const lingerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (activeAlert === null) return
    if (activeAlert.cameraId !== propCameraId) return 

    setShowViolence(true)
    setVisibleAlert(activeAlert)

    if (lingerTimerRef.current !== null) clearTimeout(lingerTimerRef.current)
    lingerTimerRef.current = setTimeout(() => setShowViolence(false), OVERLAY_LINGER_MS)

    return () => {
      if (lingerTimerRef.current !== null) clearTimeout(lingerTimerRef.current)
    }
  }, [activeAlert?.id, propCameraId])

  const threatConfidence = visibleAlert?.threatConfidence ?? visibleAlert?.confidence ?? 0
  const modelConfidence = visibleAlert?.modelConfidence ?? visibleAlert?.confidence ?? 0
  const confidence = visibleAlert?.confidence ?? 0
  const cameraId = visibleAlert?.cameraId ?? propCameraId;
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



  // When switching to a demo clip, show loading overlay for DEMO_LOADING_MS to let backend worker start
  useEffect(() => {
    if (!isDemo) { setDemoLoading(false); return }
    setDemoLoading(true)
    setStreamError(false)
    setDemoStreamError(false)
    setStreamKey(k => k + 1)
    if (demoLoadTimerRef.current) clearTimeout(demoLoadTimerRef.current)
    demoLoadTimerRef.current = setTimeout(() => setDemoLoading(false), DEMO_LOADING_MS)
    return () => { if (demoLoadTimerRef.current) clearTimeout(demoLoadTimerRef.current) }
  }, [propCameraId, isDemo])

  const streamSrc = isPlaying ? `${API_BASE}/video_feed?camera_id=${propCameraId}&k=${streamKey}` : undefined
  // For demo clips: use MJPEG stream (same as live cameras) — AVI files cannot be played natively in Chrome.
  // Backend analysis is unaffected; only the visual playback source changes.
  const demoMjpegSrc = isDemo && !demoLoading ? `${API_BASE}/video_feed?camera_id=${propCameraId}&k=${streamKey}` : undefined
  const isLiveDemoMode = LIVE_DEMO_URL.trim().length > 0

  return (
    <div className="flex h-full flex-col">


      {/* ── Status Banner ── */}
      <div className={cn("flex items-center gap-2 border-b px-4 py-2 transition-all duration-700", showViolence ? "border-danger/40 bg-danger/10" : "border-border bg-card/60")}>
        {showViolence ? (
          <><span className="flex h-2.5 w-2.5 bg-danger rounded-full animate-ping"/><span className="text-sm font-bold text-danger">⚠ VIOLENCE DETECTED — THREAT {threatConfidence.toFixed(1)}% | MODEL {modelConfidence.toFixed(1)}%</span></>
        ) : (
          <><span className="flex h-2.5 w-2.5 bg-success rounded-full animate-pulse"/><span className="text-sm font-semibold text-success">MONITORING — No Threat Detected</span>
          <span className="ml-auto flex items-center gap-1.5 font-mono text-[10px] text-muted-foreground">
             {propCameraId} —{" "}
             {CAMERAS.find(c => c.id === propCameraId)?.isLive
              ? <span className="text-red-400 font-bold">🔴 LIVE</span>
              : CAMERAS.find(c => c.id === propCameraId)?.isDemo
              ? <span className="text-amber-400 font-bold">🎬 DEMO</span>
              : <span>Playback</span>
            }
          </span></>
        )}
      </div>

      {/* ── Video Area ── */}
      <div className="relative flex-1 overflow-hidden bg-black">
        {privacyMode && <div className="absolute inset-0 z-30 flex items-center justify-center backdrop-blur-2xl"><span className="border border-danger/40 bg-black/60 px-4 py-1.5 font-mono text-sm text-danger">PRIVACY MODE — FEED REDACTED</span></div>}

        {/* Demo loading overlay — shown while backend worker is starting */}
        {isDemo && demoLoading && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-black/90">
            <Loader2 className="h-8 w-8 animate-spin text-amber-400" />
            <p className="font-mono text-sm font-semibold text-amber-400">Starting demo analysis…</p>
            <p className="font-mono text-[11px] text-muted-foreground/60">Loading AI model and clip</p>
          </div>
        )}

        {/* Live camera offline state */}
        {streamError && !isDemo && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-background/90">
            <WifiOff className="h-10 w-10 text-muted-foreground/50" />
            {CAMERAS.find(c => c.id === propCameraId)?.isLive ? (
              <>
                <p className="font-mono text-sm font-semibold text-muted-foreground">No live camera connected</p>
                <p className="font-mono text-[11px] text-muted-foreground/60">Connect {propCameraId} to begin live monitoring</p>
              </>
            ) : (
              <p className="font-mono text-sm text-muted-foreground">Stream unavailable</p>
            )}
            <Button size="sm" onClick={() => { setStreamError(false); setStreamKey((k) => k + 1) }}>Retry</Button>
          </div>
        )}

        {/* Demo stream error state */}
        {isDemo && demoStreamError && !demoLoading && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-background/90">
            <WifiOff className="h-10 w-10 text-amber-400/70" />
            <p className="font-mono text-sm font-semibold text-amber-400">Demo stream unavailable</p>
            <p className="font-mono text-[11px] text-muted-foreground/60">Backend worker may still be starting</p>
            <Button size="sm" onClick={() => { setDemoStreamError(false); setStreamKey((k) => k + 1) }}>Retry</Button>
          </div>
        )}

        {/* Demo clip: MJPEG stream via <img> — AVI files are not natively playable in Chrome.
            The MJPEG feed is served by the same backend worker started via /demo_start/{id}.
            Backend AI analysis and alert routing are completely unchanged. */}
        {isDemo && !isLiveDemoMode && demoMjpegSrc && !demoStreamError && (
          <img
            key={demoMjpegSrc}
            src={demoMjpegSrc}
            className="h-full w-full object-contain"
            onError={() => setDemoStreamError(true)}
          />
        )}

        {/* Live camera: MJPEG stream via img tag */}
        {!isDemo && !streamError && !isLiveDemoMode && (
          <img key={streamKey} src={streamSrc} className="h-full w-full object-cover" onError={() => setStreamError(true)} />
        )}

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

        <div className="pointer-events-none absolute bottom-10 left-3 z-20 flex items-center gap-2"><span className="font-mono text-[10px] text-white/60">{timestamp}</span><span className="text-[10px] text-white/30">|</span><span className="font-mono text-[10px] text-primary">{cameraId}</span></div>
      </div>

      {/* ── Controls Bar ── */}
      <div className="flex items-center justify-between border-t border-border bg-card px-4 py-2">
        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setIsPlaying((p) => !p)}>{isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}</Button>
      </div>
    </div>
  )
})
