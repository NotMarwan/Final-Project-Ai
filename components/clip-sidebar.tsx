"use client"

import React, { useState, useCallback, useEffect, useRef } from "react"
import { Card } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Play, Clock, Camera, Trash2, Loader2, X } from "lucide-react"
import { cn } from "@/lib/utils"
import type { LiveAlert } from "@/components/video-player"
import { IncidentReplay } from "./incident-replay"
import type { ThreatBox } from "@/lib/detection-types"

function buildReplayThreatBoxes(alert: LiveAlert): ThreatBox[] {
  const boxes: ThreatBox[] = []
  if (alert.weaponBbox) {
    boxes.push({
      id: "weapon-replay",
      type: "weapon",
      weaponType: alert.weaponLabels?.[0]?.toLowerCase().includes("knife") ? "knife" : "gun",
      bbox: alert.weaponBbox,
      confidence: alert.weaponScore ?? alert.confidence,
      color: [220, 38, 38],
      label: alert.weaponLabels?.[0]?.toUpperCase() ?? "WEAPON",
    })
  }
  if (alert.violenceBbox && boxes.length === 0) {
    boxes.push({
      id: "violence-replay",
      type: "violence",
      bbox: alert.violenceBbox,
      confidence: alert.confidence,
      color: [239, 68, 68],
      label: "VIOLENCE",
    })
  }
  return boxes
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

function getClipUrl(alert: LiveAlert): string {
  return alert.clipUrl ?? `${API_BASE}/clips/${alert.id}`
}

const DEMO_CAMERA_IDS = new Set(["EXAMPLE-01", "EXAMPLE-02", "EXAMPLE-03"])
const isDemoAlert = (alert: LiveAlert) => DEMO_CAMERA_IDS.has(alert.cameraId)

function DemoClipReplay({ alert }: { alert: LiveAlert }) {
  const [phase, setPhase] = useState<"loading" | "playing" | "stopped">("loading")
  const [streamKey, setStreamKey] = useState(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false

    const run = async () => {
      setPhase("loading")
      try {
        await fetch(`${API_BASE}/demo_start/${alert.cameraId}`, { method: "POST" })
      } catch { /* backend may already be running */ }
      if (cancelled) return
      setStreamKey(k => k + 1)
      setPhase("playing")
      timerRef.current = setTimeout(() => {
        if (cancelled) return
        setPhase("stopped")
        fetch(`${API_BASE}/demo_stop/${alert.cameraId}`, { method: "DELETE" }).catch(() => {})
      }, 4000)
    }

    void run()
    return () => {
      cancelled = true
      if (timerRef.current) clearTimeout(timerRef.current)
      fetch(`${API_BASE}/demo_stop/${alert.cameraId}`, { method: "DELETE" }).catch(() => {})
    }
  }, [alert.cameraId])

  const handleReplay = async () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setPhase("loading")
    try {
      await fetch(`${API_BASE}/demo_start/${alert.cameraId}`, { method: "POST" })
    } catch { /* ignore */ }
    setStreamKey(k => k + 1)
    setPhase("playing")
    timerRef.current = setTimeout(() => {
      setPhase("stopped")
      fetch(`${API_BASE}/demo_stop/${alert.cameraId}`, { method: "DELETE" }).catch(() => {})
    }, 4000)
  }

  return (
    <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden shadow-xl border border-white/10">
      {phase === "loading" && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-black">
          <Loader2 className="h-6 w-6 animate-spin text-amber-400" />
          <p className="font-mono text-xs text-amber-400">Starting demo replay…</p>
        </div>
      )}
      {phase === "playing" && (
        <img
          key={streamKey}
          src={`${API_BASE}/video_feed?camera_id=${alert.cameraId}&k=${streamKey}`}
          className="h-full w-full object-contain"
          alt="Demo replay"
        />
      )}
      {phase === "stopped" && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-black/80">
          <p className="font-mono text-xs text-muted-foreground">Replay ended</p>
          <Button size="sm" onClick={() => void handleReplay()}>Replay</Button>
        </div>
      )}
      <div className="absolute top-2 left-2 z-20">
        <Badge variant="secondary" className="text-[9px] px-1.5 py-0 bg-amber-500/20 text-amber-400 border border-amber-500/30 font-bold uppercase tracking-wider">
          Demo replay
        </Badge>
      </div>
    </div>
  )
}

interface ClipSidebarProps {
  alerts: LiveAlert[]
  selectedAlertId?: string | null
  onSelectAlert: (alert: LiveAlert) => void
  onDeleteClip?: (alertId: string) => void
}

export function ClipSidebar({ 
  alerts, 
  selectedAlertId, 
  onSelectAlert,
  onDeleteClip 
}: ClipSidebarProps) {
  const [modalAlert, setModalAlert] = useState<LiveAlert | null>(null)

  // All alerts are potential clips — URL is derived from alert.id if not present
  const clips = alerts

  const handlePlayClip = useCallback((alert: LiveAlert) => {
    setModalAlert(alert)
    onSelectAlert(alert)
  }, [onSelectAlert])

  const formatTime = (timestamp: string) => {
    return timestamp
  }

  return (
    <div className="flex flex-col h-full bg-card/30 border-r border-border">
      {/* Header */}
      <div className="p-3 border-b border-border">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Play className="h-4 w-4" />
          Clip Review
          <Badge variant="secondary" className="ml-auto">
            {clips.length}
          </Badge>
        </h3>
      </div>

      {/* Clip list */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-2">
          {clips.length === 0 ? (
            <div className="text-center text-muted-foreground text-sm py-8">
              No video clips available yet.
            </div>
          ) : (
            clips.map((alert: any) => (
              <Card
                key={alert.id}
                className={`p-2 cursor-pointer transition-colors hover:bg-accent ${
                  selectedAlertId === alert.id ? "border-primary bg-accent" : ""
                }`}
                onClick={() => handlePlayClip(alert)}
              >
                <div className="flex items-start gap-2">
                  {/* Thumbnail placeholder */}
                  <div className="w-16 h-12 bg-muted rounded flex items-center justify-center flex-shrink-0">
                    <Play className="h-4 w-4 text-muted-foreground" />
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1 mb-1">
                      <Camera className="h-3 w-3 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">
                        {alert.cameraId}
                      </span>
                      <span className="text-xs text-muted-foreground ml-auto flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {formatTime(alert.timestamp)}
                      </span>
                    </div>
                    <p className="text-xs font-medium truncate">
                      {alert.type} Detected
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge 
                        variant="secondary" 
                        className={cn(
                          "text-[9px] px-1.5 py-0 font-mono",
                          alert.severity === "critical" ? "bg-danger/20 text-danger" : "bg-primary/20 text-primary"
                        )}
                      >
                        {Math.round(alert.confidence)}%
                      </Badge>
                      <Badge variant="outline" className="text-[9px] px-1.5 py-0 uppercase tracking-tighter opacity-70">
                        {alert.threatType ?? "violence"}
                      </Badge>
                      {onDeleteClip && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 ml-auto"
                          onClick={(e) => {
                            e.stopPropagation()
                            onDeleteClip(alert.id)
                          }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              </Card>
            ))
          )}
        </div>
      </ScrollArea>

      {/* Fullscreen clip modal */}
      {modalAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-2xl">
            <button
              onClick={() => setModalAlert(null)}
              className="absolute -top-10 right-0 text-white/70 hover:text-white text-sm font-medium flex items-center gap-1"
            >
              <X className="h-4 w-4" /> Close
            </button>
            {isDemoAlert(modalAlert) ? (
              <DemoClipReplay key={modalAlert.id} alert={modalAlert} />
            ) : (
              <IncidentReplay
                clipUrl={getClipUrl(modalAlert)}
                threatType={modalAlert.threatType === "weapon" ? "weapon" : "violence"}
                confidence={Math.round(modalAlert.confidence)}
                location={modalAlert.location}
                timestamp={modalAlert.timestamp}
                autoPlay
                className="w-full"
                threatBoxes={buildReplayThreatBoxes(modalAlert)}
                alertVideoWidth={modalAlert.alertVideoWidth}
                alertVideoHeight={modalAlert.alertVideoHeight}
              />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
