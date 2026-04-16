"use client"

import { memo } from "react"
import { Bell, ShieldAlert, Camera, MapPin, Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { LiveAlert } from "@/components/video-player"

interface AlertFeedProps {
  alerts: LiveAlert[]
  selectedAlertId: string | null
  onSelectAlert: (alert: LiveAlert) => void
}

export const AlertFeed = memo(function AlertFeed({ alerts, selectedAlertId, onSelectAlert }: AlertFeedProps) {
  return (
    <div className="flex flex-col h-full">
      {/* الهيدر ثابت */}
      <div className="flex flex-shrink-0 items-center gap-2.5 border-b border-border px-4 py-3">
        <div className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-danger/10 text-danger border border-danger/20">
          <Bell className="h-4 w-4" />
          <span className="absolute -right-1 -top-1 flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-danger opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3 w-3 bg-danger border-2 border-background"></span>
          </span>
        </div>
        <div>
          <h2 className="text-sm font-bold tracking-tight">Live Incident Feed</h2>
          <p className="text-[11px] text-muted-foreground">Real-time violent activity alerts</p>
        </div>
        <Badge variant="outline" className="ml-auto font-mono text-xs border-danger/30 text-danger bg-danger/5">
          {alerts.length}
        </Badge>
      </div>

      {/* منطقة القائمة مع السحاب (overflow-y-auto) */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-2">
        {alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-10 text-center text-muted-foreground/60">
            <ShieldAlert className="h-10 w-10 opacity-30" />
            <p className="text-xs font-medium">Monitoring...</p>
          </div>
        ) : (
          alerts.map((alert) => {
            const isSelected = alert.id === selectedAlertId
            return (
              <button
                key={alert.id}
                onClick={() => onSelectAlert(alert)}
                className={cn(
                  "block w-full text-left rounded-lg border p-3 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/40",
                  isSelected
                    ? "bg-primary/10 border-primary/30 shadow-md scale-[1.01]"
                    : "bg-card hover:bg-secondary/50 border-border hover:border-border-hover"
                )}
              >
                <div className="flex items-center gap-2 mb-2">
                  <Badge className={cn("text-[9px] uppercase font-bold", alert.severity === "critical" ? "bg-danger" : "bg-warning")}>
                    {alert.severity}
                  </Badge>
                  <span className="font-mono text-[10px] text-muted-foreground ml-auto">{alert.timestamp}</span>
                </div>
                
                <h3 className="text-xs font-semibold mb-2 flex items-center gap-1.5">
                  <ShieldAlert className="h-3.5 w-3.5 text-danger" />
                  {alert.type} Incident Detected
                </h3>
                
                <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-[10px] text-muted-foreground bg-background/50 rounded p-1.5 border border-border/50">
                  <div className="flex items-center gap-1"><Camera className="h-3 w-3"/>{alert.cameraId}</div>
                  <div className="flex items-center gap-1"><MapPin className="h-3 w-3"/>{alert.location}</div>
                </div>
              </button>
            )
          })
        )}
      </div>
    </div>
  )
})
