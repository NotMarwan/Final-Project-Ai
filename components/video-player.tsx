"use client"

import { useState, useEffect, useRef, useMemo, memo, useCallback } from "react"
import {
  Repeat, Timer, Radio, Play, Pause, Maximize2,
  WifiOff, Loader2, Camera, Layers,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { DetectionCategory, CategoryScore } from "@/lib/detection-types"
import { WebRTCPlayer } from "@/components/webrtc-player"
import { CanvasOverlay } from "@/components/canvas-overlay"
import { useDetectionStream } from "@/hooks/use-detection-stream"
import { OverlaySettingsPanel } from "@/components/overlay-settings"

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
  personCount?: number
  overlaySettings?: {
    showBoxes: boolean
    showLabels: boolean
    showFps: boolean
    showPersonCount: boolean
    showTimestamp: boolean
    showThreatBadge: boolean
    opacity: number
    boxThickness: number
    labelStyle: "chip" | "plain"
  }
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

export const VideoPlayer = memo(function VideoPlayer({ cameraId: propCameraId, activeAlert, privacyMode, personCount = 0, overlaySettings }: VideoPlayerProps) {
  const [isPlaying,     setIsPlaying]     = useState(true)
  const [activeControl, setActiveControl] = useState<string | null>(null)
  const [streamError,   setStreamError]   = useState(false)
  const [streamKey,     setStreamKey]     = useState(0)
  const [demoLoading,   setDemoLoading]   = useState(false)
  const [demoStreamError, setDemoStreamError] = useState(false)
  const [webrtcUrl, setWebrtcUrl] = useState<string | null>(null)
  const [webrtcReady, setWebrtcReady] = useState(false)
  const [webrtcFailed, setWebrtcFailed] = useState(false)
  const demoLoadTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isDemo = CAMERAS.find(c => c.id === propCameraId)?.isDemo ?? false



  const [showViolence, setShowViolence] = useState(false)
  const [visibleAlert, setVisibleAlert] = useState<LiveAlert | null>(null)
  const [showOverlays, setShowOverlays] = useState(() => overlaySettings?.showBoxes ?? true)
  const lingerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const videoContainerRef = useRef<HTMLDivElement>(null)
  const [containerSize, setContainerSize] = useState({ width: 1280, height: 720 })

  const { data: detectionData } = useDetectionStream(propCameraId)

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

  // Resize observer to track video container dimensions for canvas scaling
  useEffect(() => {
    const el = videoContainerRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setContainerSize({ width, height })
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

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
    setWebrtcReady(false)
    setWebrtcFailed(false)
    setStreamKey(k => k + 1)
    if (demoLoadTimerRef.current) clearTimeout(demoLoadTimerRef.current)
    demoLoadTimerRef.current = setTimeout(() => setDemoLoading(false), DEMO_LOADING_MS)
    return () => { if (demoLoadTimerRef.current) clearTimeout(demoLoadTimerRef.current) }
  }, [propCameraId, isDemo])

  // Background WebRTC discovery — never blocks MJPEG
  useEffect(() => {
    if (!propCameraId) return
    setWebrtcUrl(null)
    setWebrtcReady(false)
    setWebrtcFailed(false)
    fetch(`${API_BASE}/api/webrtc/${propCameraId}`)
      .then((res) => {
        if (res.ok) return res.json()
        throw new Error("WebRTC not available")
      })
      .then((data) => {
        setWebrtcUrl(data.url)
      })
      .catch(() => {
        setWebrtcFailed(true)
      })
  }, [propCameraId])

  const streamSrc = isPlaying ? `${API_BASE}/video_feed?camera_id=${propCameraId}&k=${streamKey}` : undefined
  // For demo clips: use MJPEG stream (same as live cameras) — AVI files cannot be played natively in Chrome.
  // Backend analysis is unaffected; only the visual playback source changes.
  const demoMjpegSrc = isDemo && !demoLoading ? `${API_BASE}/video_feed?camera_id=${propCameraId}&k=${streamKey}` : undefined
  const isLiveDemoMode = LIVE_DEMO_URL.trim().length > 0

  return (
    <div className="flex h-full flex-col">


      {/* ── Status Banner ── */}
      <div className={cn("flex items-center gap-2 border-b px-4 py-2.5 transition-all duration-700 relative overflow-hidden", showViolence ? "border-danger/40 bg-danger/10" : "border-border/60 bg-card/60")}>
        {/* Animated shimmer for status bar */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className={cn("absolute inset-0 bg-gradient-to-r from-transparent via-primary/5 to-transparent opacity-0 transition-opacity duration-700", showViolence ? "opacity-0" : "opacity-100")}>
            <div className="absolute inset-0 animate-shimmer" />
          </div>
        </div>

        {showViolence ? (
          <div className="flex items-center gap-3 relative z-10">
            <div className="relative">
              <span className="absolute inset-0 bg-danger/30 rounded-full blur-md animate-ambient-pulse" />
              <span className="relative flex h-3 w-3 bg-danger rounded-full animate-ping" />
            </div>
            <span className="text-sm font-black uppercase tracking-widest text-danger animate-glitch">
              ⚠ VIOLENCE DETECTED — THREAT {threatConfidence.toFixed(1)}% | MODEL {modelConfidence.toFixed(1)}%
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-2 relative z-10">
            <div className="relative">
              <span className="absolute inset-0 bg-success/20 rounded-full blur-md animate-ambient-pulse" />
              <span className="relative flex h-2.5 w-2.5 bg-success rounded-full animate-pulse" />
            </div>
            <span className="text-sm font-bold tracking-wide text-success">MONITORING — No Threat Detected</span>
            <span className="ml-auto flex items-center gap-3 font-mono text-[10px] text-muted-foreground">
              {(personCount ?? 0) > 0 && (
                <span className="flex items-center gap-1 text-cyan-400 font-semibold">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  PERSONS: {personCount}
                </span>
              )}
              {propCameraId} —{" "}
              {CAMERAS.find(c => c.id === propCameraId)?.isLive
               ? <span className="text-red-400 font-bold animate-ambient-pulse">🔴 LIVE</span>
               : CAMERAS.find(c => c.id === propCameraId)?.isDemo
               ? <span className="text-amber-400 font-bold">🎬 DEMO</span>
               : <span>Playback</span>
             }
            </span>
          </div>
        )}
      </div>

      {/* ── Video Area ── */}
      <div ref={videoContainerRef} className={cn("relative flex-1 overflow-hidden bg-black transition-all duration-500", showViolence ? "animate-shake" : "")}>
        {/* Dot grid atmospheric background */}
        <div className="absolute inset-0 bg-dot-grid opacity-30 pointer-events-none z-0" />

        {privacyMode && <div className="absolute inset-0 z-30 flex items-center justify-center backdrop-blur-2xl"><span className="border border-danger/40 bg-black/60 px-4 py-1.5 font-mono text-sm text-danger">PRIVACY MODE — FEED REDACTED</span></div>}

        {/* Demo loading overlay — shown while backend worker is starting */}
        {isDemo && demoLoading && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-black/90">
            <div className="relative">
              <div className="absolute inset-0 bg-amber-500/20 rounded-full blur-2xl animate-ambient-pulse" />
              <Loader2 className="h-10 w-10 animate-spin text-amber-400 relative z-10" />
            </div>
            <p className="font-mono text-sm font-semibold text-amber-400">Starting demo analysis…</p>
            <p className="font-mono text-[11px] text-muted-foreground/60">Loading AI model and clip</p>
            {/* Loading progress bar */}
            <div className="w-48 h-1 bg-secondary rounded-full overflow-hidden mt-2">
              <div className="h-full bg-amber-500 animate-shimmer rounded-full" style={{ width: '60%' }} />
            </div>
          </div>
        )}

        {/* Live camera offline state */}
        {streamError && !isDemo && (
          <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-background/90">
            <WifiOff className="h-12 w-12 text-muted-foreground/50" />
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
            <WifiOff className="h-12 w-12 text-amber-400/70" />
            <p className="font-mono text-sm font-semibold text-amber-400">Demo stream unavailable</p>
            <p className="font-mono text-[11px] text-muted-foreground/60">Backend worker may still be starting</p>
            <Button size="sm" onClick={() => { setDemoStreamError(false); setStreamKey((k) => k + 1) }}>Retry</Button>
          </div>
        )}

        {/* Demo clip: MJPEG stream via <img> */}
        {isDemo && !isLiveDemoMode && demoMjpegSrc && !demoStreamError && (
          <>
            <img
              key={demoMjpegSrc}
              src={demoMjpegSrc}
              className="h-full w-full object-contain"
              onError={() => setDemoStreamError(true)}
            />
            <CanvasOverlay
              data={detectionData}
              videoWidth={1280}
              videoHeight={720}
              containerWidth={containerSize.width}
              containerHeight={containerSize.height}
              showBoxes={showOverlays}
              showLabels={showOverlays}
              opacity={overlaySettings?.opacity ?? 85}
              boxThickness={overlaySettings?.boxThickness ?? 2}
              labelStyle={overlaySettings?.labelStyle ?? "chip"}
            />
          </>
        )}

        {/* Live camera: MJPEG stream via img tag (base layer) */}
        {!isDemo && !streamError && !isLiveDemoMode && (
          <>
            <div className="absolute inset-0">
              <img key={streamKey} src={streamSrc} className={`h-full w-full object-cover ${webrtcReady ? "invisible" : "visible"}`} onError={() => setStreamError(true)} />
              {webrtcUrl && !webrtcFailed && (
                <WebRTCPlayer
                  streamUrl={webrtcUrl}
                  camId={propCameraId}
                  onError={() => setWebrtcFailed(true)}
                  onConnected={() => setWebrtcReady(true)}
                  className={`absolute inset-0 ${webrtcReady ? "z-10" : "z-0"}`}
                />
              )}
            </div>
            <CanvasOverlay
              data={detectionData}
              videoWidth={1280}
              videoHeight={720}
              containerWidth={containerSize.width}
              containerHeight={containerSize.height}
              showBoxes={showOverlays}
              showLabels={showOverlays}
              opacity={overlaySettings?.opacity ?? 85}
              boxThickness={overlaySettings?.boxThickness ?? 2}
              labelStyle={overlaySettings?.labelStyle ?? "chip"}
            />
          </>
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

        {/* Threat border pulse */}
        {showViolence && <div className="pointer-events-none absolute inset-0 z-10 border-[3px] border-danger animate-pulse-danger" />}

        {/* Scan line overlay */}
        <div className={cn("pointer-events-none absolute inset-0 z-10 transition-opacity duration-700", showViolence ? "opacity-60" : "opacity-20")} style={{ background: "repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.08) 2px,rgba(0,0,0,0.08) 4px)" }} />

        {/* Animated scan line */}
        {!showViolence && (
          <div className="pointer-events-none absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-primary/30 to-transparent z-10 animate-scan-video opacity-40" />
        )}

        {/* Threat overlay banner */}
        {showViolence && (
          <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center pt-6">
            <div className="flex items-center gap-3 rounded-lg border border-danger/50 bg-black/70 px-6 py-3 backdrop-blur-sm animate-alert-enter">
              <div className="relative">
                <span className="absolute inset-0 bg-danger/30 rounded-full blur-md animate-ambient-pulse" />
                <span className="relative flex h-3 w-3 bg-danger rounded-full animate-ping" />
              </div>
              <span className="font-mono text-base font-black uppercase tracking-wider text-danger drop-shadow-lg animate-glitch">⚠ VIOLENCE DETECTED</span>
              <div className="relative">
                <span className="absolute inset-0 bg-danger/30 rounded-full blur-md animate-ambient-pulse" />
                <span className="relative flex h-3 w-3 bg-danger rounded-full animate-ping" />
              </div>
            </div>
          </div>
        )}

        {/* Tactical HUD corners - normal state */}
        {!showViolence && (
          <>
            <div className="hud-corner hud-corner-tl" />
            <div className="hud-corner hud-corner-tr" />
            <div className="hud-corner hud-corner-bl" />
            <div className="hud-corner hud-corner-br" />
          </>
        )}
        {/* Tactical HUD corners - threat state */}
        {showViolence && (
          <div className="hud-corner-threat">
            <div className="hud-corner hud-corner-tl border-danger/80" />
            <div className="hud-corner hud-corner-tr border-danger/80" />
            <div className="hud-corner hud-corner-bl border-danger/80" />
            <div className="hud-corner hud-corner-br border-danger/80" />
          </div>
        )}

        {showViolence && visibleAlert && <div className="pointer-events-none absolute left-3 top-3 z-20 animate-alert-enter"><Badge className="h-5 border-danger/40 bg-danger/20 text-danger glow-danger">{visibleAlert.severity}</Badge></div>}
        {isLiveDemoMode && <div className="pointer-events-none absolute left-3 top-3 z-20"><Badge className="h-5 border-primary/40 bg-primary/20 text-primary">LIVE DEMO</Badge></div>}

        {/* Animated REC indicator */}
        <div className="pointer-events-none absolute right-3 top-3 z-20 flex items-center gap-1.5">
          <span className={cn("h-2.5 w-2.5 rounded-full", showViolence ? "bg-danger animate-ambient-pulse" : "bg-danger animate-pulse")} />
          <span className={cn("font-mono text-[10px] font-bold tracking-widest", showViolence ? "text-danger animate-threat-flash" : "text-danger/70")}>REC</span>
        </div>

        {/* Timestamp and camera ID overlay */}
        <div className="pointer-events-none absolute bottom-10 left-3 z-20 flex items-center gap-2">
          <span className="font-mono text-[10px] text-white/60 backdrop-blur-sm px-1.5 py-0.5 rounded bg-black/30">{timestamp}</span>
          <span className="text-[10px] text-white/30">|</span>
          <span className="font-mono text-[10px] text-primary/80 backdrop-blur-sm px-1.5 py-0.5 rounded bg-black/30">{cameraId}</span>
        </div>

        {/* Confidence score overlay */}
        {showViolence && visibleAlert && (
          <div className="pointer-events-none absolute bottom-10 right-3 z-20">
            <div className="backdrop-blur-sm bg-black/50 rounded-lg border border-danger/30 px-3 py-1.5">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-[9px] text-danger/80 uppercase">Threat</span>
                <span className="font-mono text-xs font-bold text-danger">{(visibleAlert.threatConfidence ?? 0).toFixed(1)}%</span>
              </div>
              <div className="w-20 h-1 bg-secondary rounded-full overflow-hidden">
                <div className="h-full bg-danger animate-shimmer rounded-full" style={{ width: `${visibleAlert.threatConfidence ?? 0}%` }} />
              </div>
            </div>
          </div>
        )}

        {/* ── CSS HUD Overlays (crisp, rendered by browser) ── */}
        {showOverlays && (
          <>
            {/* Top-left: Person count + FPS */}
            <div className="pointer-events-none absolute top-3 left-3 z-20 flex flex-col gap-1">
              <div className="flex items-center gap-2 backdrop-blur-sm bg-black/60 rounded px-2 py-1 border border-white/10">
                <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
                <span className="font-mono text-xs text-cyan-400 font-bold">
                  PERSONS: {(detectionData?.personCount ?? personCount ?? 0)}
                </span>
              </div>
              <div className="font-mono text-[10px] text-white/50 backdrop-blur-sm bg-black/40 rounded px-2 py-0.5">
                {detectionData?.fps?.toFixed(0) ?? "--"} FPS
              </div>
            </div>

            {/* Bottom-left: Camera ID + Timestamp */}
            <div className="pointer-events-none absolute bottom-14 left-3 z-20 flex items-center gap-2">
              <span className="font-mono text-[10px] text-primary/80 backdrop-blur-sm bg-black/60 rounded px-1.5 py-0.5 border border-white/10">
                {propCameraId}
              </span>
              <span className="font-mono text-[10px] text-white/40">
                {visibleAlert?.timestamp ?? new Date().toLocaleTimeString()}
              </span>
            </div>

            {/* Bottom-right: Status badge */}
            <div className="pointer-events-none absolute bottom-14 right-3 z-20">
              {detectionData?.isThreat ? (
                <div className="backdrop-blur-sm bg-black/70 rounded border border-danger/50 px-3 py-1 animate-pulse">
                  <span className="font-mono text-xs font-bold text-danger">
                    THREAT {(detectionData.threatConfidence ?? 0).toFixed(0)}%
                  </span>
                </div>
              ) : (
                <div className="backdrop-blur-sm bg-black/40 rounded px-2 py-1">
                  <span className="font-mono text-[10px] text-success font-semibold">● NORMAL</span>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* ── Controls Bar ── */}
      <div className="flex items-center justify-between border-t border-border bg-card px-4 py-2">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setIsPlaying((p) => !p)}>{isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}</Button>
        </div>
        <div className="flex items-center gap-2">
          <OverlaySettingsPanel
            settings={{
              showBoxes: showOverlays,
              showLabels: showOverlays,
              showFps: true,
              showPersonCount: true,
              showTimestamp: true,
              showThreatBadge: true,
              opacity: overlaySettings?.opacity ?? 85,
              boxThickness: overlaySettings?.boxThickness ?? 2,
              labelStyle: overlaySettings?.labelStyle ?? "chip",
            }}
            onChange={(s) => {
              setShowOverlays(s.showBoxes)
            }}
          />
          {detectionData?.fps && (
            <span className="font-mono text-[10px] text-muted-foreground ml-2">{detectionData.fps.toFixed(0)} FPS</span>
          )}
        </div>
      </div>
    </div>
  )
})
