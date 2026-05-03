"use client"

import React, { useState, useCallback } from "react"
import { Card } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Play, Clock, Camera, Trash2 } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"
import { ClipPlayer } from "./clip-player"

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
  const [activeClipUrl, setActiveClipUrl] = useState<string | undefined>()
  const [activeClipName, setActiveClipName] = useState<string>("")

  // Filter alerts that have clips
  // Note: Using any here because clipUrl might not be in LiveAlert type yet
  const clips = alerts.filter((a: any) => a.clipUrl)

  const handlePlayClip = useCallback((alert: LiveAlert) => {
    const alertAny = alert as any
    if (alertAny.clipUrl) {
      setActiveClipUrl(alertAny.clipUrl)
      setActiveClipName(`Clip-${alert.id.slice(0, 8)}`)
      onSelectAlert(alert)
    }
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

      {/* Active clip player */}
      {activeClipUrl && (
        <div className="p-3 border-b border-border">
          <ClipPlayer
            clipUrl={activeClipUrl}
            clipName={activeClipName}
            autoPlay
            className="aspect-video"
          />
        </div>
      )}

      {/* Clip list */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-2">
          {clips.length === 0 ? (
            <div className="text-center text-muted-foreground text-sm py-8">
              No clips available yet
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
                      <Badge variant="outline" className="text-[10px] px-1 py-0">
                        {Math.round(alert.confidence * 100)}%
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
    </div>
  )
}
