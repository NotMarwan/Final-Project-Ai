"use client"

import { useState } from "react"
import { Repeat, Timer, Radio, Play, Pause, Maximize2, WifiOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

// ─── Types ────────────────────────────────────────────────────────────────────

export interface LiveAlert {
  id: string
  timestamp: string
  isoTime: string
  confidence: number
  type: "Violence"
  severity: "critical" | "high" | "medium"
  cameraId: string
  location: string
}

interface VideoPlayerProps {
  /** The most recent alert — drives the warning banner & confidence meter */
  activeAlert: LiveAlert | null
  privacyMode: boolean
}

// ─── Constants ────────────────────────────────────────────────────────────────

const VIDEO_FEED_URL  = "http://localhost:8000/video_feed"
const CAMERA_LABEL    = "CAM-01 — Live Feed"

// ─── Component ────────────────────────────────────────────────────────────────

export function VideoPlayer({ activeAlert, privacyMode }: VideoPlayerProps) {
  const [isPlaying,     setIsPlaying]     = useState(true)
  const [activeControl, setActiveControl] = useState<string | null>(null)
  const [streamError,   setStreamError]   = useState(false)

  const isViolent    = activeAlert !== null
  const confidence   = activeAlert?.confidence ?? 0
  const cameraId     = activeAlert?.cameraId ?? "CAM-01"
  const timestamp    = activeAlert?.timestamp ?? "--:--:-- UTC"

  return (
    <div className="flex h-full flex-col">

      {/* ── Warning / Safe banner ────────────────────────────────────────── */}
      <div
        className={cn(
          "flex items-center gap-2 border-b px-4 py-2 transition-colors duration-500",
          isViolent
            ? "border-danger/30 bg-danger/10"
            : "border-border bg-card/60"
        )}
      >
        {isViolent ? (
          <>
            {/* Pulsing danger dot */}
            <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-danger opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-danger" />
            </span>
            <span className="text-sm font-bold tracking-wide text-danger">
              ⚠ VIOLENCE DETECTED — CONFIDENCE {confidence.toFixed(1)}%
            </span>
            <div className="ml-auto flex items-center gap-1.5">
              <span className="font-mono text-[10px] uppercase text-danger/70">
                Live Alert
              </span>
            </div>
          </>
        ) : (
          <>
            <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-success" />
            </span>
            <span className="text-sm font-semibold text-success">
              MONITORING — No Threat Detected
            </span>
            <span className="ml-auto font-mono text-[10px] text-muted-foreground">
              {CAMERA_LABEL}
            </span>
          </>
        )}
      </div>

      {/* ── Live MJPEG stream ────────────────────────────────────────────── */}
      <div className="relative flex-1 overflow-hidden bg-black">

        {/* Privacy blur overlay — sits on TOP of the img */}
        {privacyMode && (
          <div className="absolute inset-0 z-20 flex items-center justify-center backdrop-blur-2xl">
            <span className="rounded-md border border-danger/40 bg-black/60 px-4 py-1.5 font-mono text-sm font-semibold text-danger">
              PRIVACY MODE — FEED REDACTED
            </span>
          </div>
        )}

        {/* Stream error fallback */}
        {streamError && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-background/80">
            <WifiOff className="h-10 w-10 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              Cannot connect to{" "}
              <code className="rounded bg-secondary px-1 text-xs">{VIDEO_FEED_URL}</code>
            </p>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setStreamError(false)}
            >
              Retry
            </Button>
          </div>
        )}

        {/* The actual live frame — MJPEG streams natively via <img> in all browsers */}
        {!streamError && (
          <img
            src={isPlaying ? VIDEO_FEED_URL : undefined}
            alt="Live CCTV feed"
            className="h-full w-full object-cover"
            onError={() => setStreamError(true)}
          />
        )}

        {/* ── HUD overlays (drawn on top of the real stream) ────────────── */}

        {/* REC badge — top-right */}
        <div className="pointer-events-none absolute right-3 top-3 z-10 flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-danger animate-pulse" />
          <span className="font-mono text-[10px] font-bold text-danger drop-shadow">
            REC
          </span>
        </div>

        {/* Severity badge — top-left (only when violent) */}
        {isViolent && activeAlert && (
          <div className="pointer-events-none absolute left-3 top-3 z-10">
            <Badge
              className={cn(
                "h-5 border px-2 font-mono text-[9px] uppercase",
                activeAlert.severity === "critical"
                  ? "border-danger/40 bg-danger/20 text-danger"
                  : activeAlert.severity === "high"
                  ? "border-warning/40 bg-warning/20 text-warning"
                  : "border-primary/40 bg-primary/20 text-primary"
              )}
            >
              {activeAlert.severity}
            </Badge>
          </div>
        )}

        {/* Timestamp + Camera ID — bottom-left */}
        <div className="pointer-events-none absolute bottom-10 left-3 z-10 flex items-center gap-2">
          <span className="font-mono text-[10px] text-white/60 drop-shadow">
            {timestamp}
          </span>
          <span className="text-[10px] text-white/30">|</span>
          <span className="font-mono text-[10px] text-primary drop-shadow">
            {cameraId}
          </span>
        </div>

        {/* Confidence meter — bottom-right */}
        {isViolent && (
          <div className="pointer-events-none absolute bottom-10 right-3 z-10 flex items-center gap-2">
            <span className="font-mono text-[10px] text-white/50 drop-shadow">
              CONF
            </span>
            <div className="h-1.5 w-20 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-danger transition-all duration-500"
                style={{ width: `${confidence}%` }}
              />
            </div>
            <span className="font-mono text-[10px] text-danger drop-shadow">
              {confidence.toFixed(1)}%
            </span>
          </div>
        )}

        {/* Red border when violence is active */}
        {isViolent && (
          <div className="pointer-events-none absolute inset-0 z-10 rounded-none border-2 border-danger/70" />
        )}
      </div>

      {/* ── Controls bar ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-t border-border bg-card px-4 py-2">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-muted-foreground hover:bg-secondary hover:text-foreground"
            onClick={() => setIsPlaying((p) => !p)}
            aria-label={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying
              ? <Pause className="h-3.5 w-3.5" />
              : <Play  className="h-3.5 w-3.5" />}
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <ControlButton
            icon={<Repeat className="h-3.5 w-3.5" />}
            label="Loop Clip"
            isActive={activeControl === "loop"}
            onClick={() => setActiveControl(activeControl === "loop" ? null : "loop")}
          />
          <ControlButton
            icon={<Timer className="h-3.5 w-3.5" />}
            label="Slow Motion"
            isActive={activeControl === "slow"}
            onClick={() => setActiveControl(activeControl === "slow" ? null : "slow")}
          />
          <ControlButton
            icon={<Radio className="h-3.5 w-3.5" />}
            label="Live Feed"
            isActive={activeControl === "live"}
            onClick={() => setActiveControl(activeControl === "live" ? null : "live")}
          />
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-muted-foreground hover:bg-secondary hover:text-foreground"
            aria-label="Fullscreen"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ControlButton({
  icon,
  label,
  isActive,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  isActive: boolean
  onClick: () => void
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn(
        "h-7 gap-1.5 px-2 text-[11px]",
        isActive
          ? "bg-primary/15 text-primary hover:bg-primary/20 hover:text-primary"
          : "text-muted-foreground hover:bg-secondary hover:text-foreground"
      )}
      onClick={onClick}
    >
      {icon}
      <span className="hidden lg:inline">{label}</span>
    </Button>
  )
}
