"use client"

import React, { useState, useEffect, useCallback } from "react"
import { Card } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Play, Clock, Camera, Download, X, Film, RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"
import type { LiveAlert } from "@/components/video-player"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

interface FolderClip {
  alertId: string
  clipUrl: string
  timestamp: string | null
  cameraId: string | null
  type: string
  confidence: number | null
  severity: string | null
  size: number
  mtime: number
}

function parseTimeFromId(alertId: string): string {
  try {
    const ms = parseInt(alertId.split("-")[1] ?? "0", 10)
    if (ms > 0) {
      return new Date(ms).toLocaleTimeString("en-GB", {
        hour: "2-digit", minute: "2-digit", second: "2-digit",
      })
    }
  } catch { /* ignore */ }
  return "—"
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

interface ClipSidebarProps {
  alerts: LiveAlert[]
  selectedAlertId?: string | null
  onSelectAlert: (alert: LiveAlert) => void
  onDeleteClip?: (alertId: string) => void
}

export function ClipSidebar({ alerts, selectedAlertId, onSelectAlert }: ClipSidebarProps) {
  const [clips, setClips] = useState<FolderClip[]>([])
  const [modalClip, setModalClip] = useState<FolderClip | null>(null)
  const [videoError, setVideoError] = useState(false)

  const alertMap = React.useMemo(() => {
    const m = new Map<string, LiveAlert>()
    for (const a of alerts) m.set(a.id, a)
    return m
  }, [alerts])

  const fetchClips = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/clips/list`)
      if (!res.ok) return
      const data = await res.json()
      setClips(data.clips as FolderClip[])
    } catch { /* ignore network errors */ }
  }, [])

  useEffect(() => {
    void fetchClips()
    const id = setInterval(() => void fetchClips(), 5000)
    return () => clearInterval(id)
  }, [fetchClips])

  const openClip = (clip: FolderClip) => {
    setModalClip(clip)
    setVideoError(false)
    const alert = alertMap.get(clip.alertId)
    if (alert) onSelectAlert(alert)
  }

  return (
    <div className="flex flex-col h-full bg-card/30 border-r border-border">
      {/* Header */}
      <div className="p-3 border-b border-border">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Film className="h-4 w-4 text-primary" />
          Evidence Clips
          <Badge variant="secondary" className="ml-auto">
            {clips.length}
          </Badge>
          <button
            onClick={() => void fetchClips()}
            className="text-muted-foreground hover:text-foreground transition-colors"
            title="Refresh"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </h3>
      </div>

      {/* Clip list */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-2">
          {clips.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
              <Film className="h-8 w-8 text-muted-foreground/20" />
              <p className="text-sm text-muted-foreground">No evidence clips yet</p>
              <p className="text-xs text-muted-foreground/60">Clips appear here when incidents are detected</p>
            </div>
          ) : (
            clips.map((clip) => {
              const alert = alertMap.get(clip.alertId)
              const displayType = (clip.type !== "unknown" ? clip.type : alert?.type) ?? "Incident"
              const displayCamera = clip.cameraId ?? alert?.cameraId ?? "—"
              const displayTime = clip.timestamp ?? parseTimeFromId(clip.alertId)
              const confidence = clip.confidence ?? alert?.confidence

              return (
                <Card
                  key={clip.alertId}
                  className={cn(
                    "p-2 cursor-pointer transition-colors hover:bg-accent",
                    selectedAlertId === clip.alertId ? "border-primary bg-accent" : "",
                  )}
                  onClick={() => openClip(clip)}
                >
                  <div className="flex items-start gap-2">
                    <div className="w-16 h-12 bg-muted rounded flex items-center justify-center flex-shrink-0">
                      <Play className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1 mb-1">
                        <Camera className="h-3 w-3 text-muted-foreground" />
                        <span className="text-xs text-muted-foreground truncate">{displayCamera}</span>
                        <span className="ml-auto text-xs text-muted-foreground flex items-center gap-1 flex-shrink-0">
                          <Clock className="h-3 w-3" />
                          {displayTime}
                        </span>
                      </div>
                      <p className="text-xs font-medium truncate">{displayType} Detected</p>
                      <div className="flex items-center gap-2 mt-1">
                        {confidence != null && (
                          <Badge variant="secondary" className="text-[9px] px-1.5 py-0 font-mono bg-danger/20 text-danger">
                            {Math.round(confidence)}%
                          </Badge>
                        )}
                        <Badge variant="outline" className="text-[9px] px-1.5 py-0 uppercase tracking-tighter opacity-70">
                          {formatSize(clip.size)}
                        </Badge>
                      </div>
                    </div>
                  </div>
                </Card>
              )
            })
          )}
        </div>
      </ScrollArea>

      {/* Video modal */}
      {modalClip && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-3xl flex flex-col gap-2">
            <button
              onClick={() => setModalClip(null)}
              className="absolute -top-9 right-0 text-white/70 hover:text-white text-sm font-medium flex items-center gap-1"
            >
              <X className="h-4 w-4" /> Close
            </button>

            {/* Clip meta */}
            <div className="flex items-center gap-2 px-1">
              <Badge variant="destructive" className="text-[10px] uppercase font-bold tracking-wider">
                Evidence
              </Badge>
              <span className="text-white/70 text-xs font-mono">
                {alertMap.get(modalClip.alertId)?.cameraId ?? modalClip.cameraId ?? "Unknown camera"}
              </span>
              <span className="ml-auto text-white/40 text-xs font-mono">
                {parseTimeFromId(modalClip.alertId)}
                {" · "}
                {formatSize(modalClip.size)}
              </span>
            </div>

            {/* Video */}
            <div className="relative bg-black rounded-xl overflow-hidden border border-white/10 shadow-2xl">
              {!videoError ? (
                <video
                  key={modalClip.alertId}
                  src={`${API_BASE}${modalClip.clipUrl}`}
                  controls
                  autoPlay
                  playsInline
                  className="w-full max-h-[72vh] object-contain bg-black"
                  onError={() => setVideoError(true)}
                />
              ) : (
                <div className="flex flex-col items-center justify-center gap-4 py-20">
                  <Film className="h-12 w-12 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">
                    Browser cannot play this format inline.
                  </p>
                  <a
                    href={`${API_BASE}${modalClip.clipUrl}`}
                    download={`${modalClip.alertId}.mp4`}
                    className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 transition-colors"
                  >
                    <Download className="h-4 w-4" />
                    Download Clip
                  </a>
                </div>
              )}
            </div>

            {/* Download link */}
            <div className="flex justify-end px-1">
              <a
                href={`${API_BASE}${modalClip.clipUrl}`}
                download={`${modalClip.alertId}.mp4`}
                className="inline-flex items-center gap-1 text-xs text-white/40 hover:text-white/70 transition-colors"
              >
                <Download className="h-3 w-3" />
                Save clip
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
