"use client"

import { memo, useState, useEffect } from "react"
import { Bell, ShieldAlert, Camera, MapPin } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { LiveAlert } from "@/components/video-player"
import { DetectionCategory, CATEGORY_LABELS, CATEGORY_COLORS } from "@/lib/detection-types"
import { CategoryFilter } from "./category-filter"

interface AlertFeedProps {
  alerts: LiveAlert[]
  selectedAlertId: string | null
  onSelectAlert: (alert: LiveAlert) => void
  selectedCategories: DetectionCategory[]
  onCategoryChange: (categories: DetectionCategory[]) => void
  categoryCounts?: Partial<Record<DetectionCategory, number>>
}

function useRelativeTime(isoTime: string) {
  const [relative, setRelative] = useState(() => formatRelative(isoTime))
  useEffect(() => {
    const id = setInterval(() => setRelative(formatRelative(isoTime)), 10_000)
    return () => clearInterval(id)
  }, [isoTime])
  return relative
}

function formatRelative(isoTime: string) {
  try {
    const diff = Date.now() - Date.parse(isoTime)
    if (Number.isNaN(diff)) return isoTime
    const sec = Math.floor(diff / 1000)
    if (sec < 60) return `${sec}s ago`
    if (sec < 3600) return `${Math.floor(sec / 60)}m ago`
    if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`
    return `${Math.floor(sec / 86400)}d ago`
  } catch {
    return isoTime
  }
}

function severityBorderColor(severity: string) {
  if (severity === "critical") return "border-l-danger"
  if (severity === "high") return "border-l-warning"
  return "border-l-primary"
}

// Extracted component so useRelativeTime is called at component top-level,
// not inside a .map() loop — fixes React Rules of Hooks violation.
function AlertItem({
  alert,
  isSelected,
  index,
  onSelect,
}: {
  alert: LiveAlert
  isSelected: boolean
  index: number
  onSelect: (alert: LiveAlert) => void
}) {
  const relativeTime = useRelativeTime(alert.isoTime)
  const severityGlow = alert.severity === "critical" ? "glow-danger" : "glow-warning"
  const borderColor = severityBorderColor(alert.severity)

  return (
    <button
      onClick={() => onSelect(alert)}
      className={cn(
        "block w-full text-left rounded-lg border border-l-[3px] p-3 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-primary/40 animate-slide-from-right",
        borderColor,
        isSelected
          ? "bg-primary/8 border-primary/40 shadow-lg shadow-primary/8 scale-[1.01]"
          : "bg-card/60 hover:bg-secondary/40 border-border/50 hover:border-border hover:shadow-md"
      )}
      style={{ animationDelay: `${Math.min(index * 50, 400)}ms` }}
    >
      {/* Top row: severity badge + relative time */}
      <div className="flex items-center justify-between mb-2">
        <div className="relative">
          <span className={cn("absolute inset-0 rounded-full blur-md animate-ambient-pulse", alert.severity === "critical" ? "bg-danger/40" : "bg-warning/40")} />
          <Badge className={cn("text-[10px] uppercase font-bold border-0", alert.severity === "critical" ? "bg-danger text-white" : "bg-warning text-black", severityGlow)}>
            {alert.severity}
          </Badge>
        </div>
        <span className="font-mono text-[10px] text-muted-foreground/70">{relativeTime}</span>
      </div>

      {/* Type label */}
      <h3 className="text-xs font-bold mb-1.5 flex items-center gap-1.5">
        <ShieldAlert className={cn("h-3.5 w-3.5", alert.severity === "critical" ? "text-danger" : "text-warning")} />
        <span className={cn(alert.severity === "critical" ? "text-danger" : "text-warning")}>
          {alert.type} Detected
        </span>
      </h3>

      {/* Meta tags */}
      <div className="flex flex-wrap gap-1 mb-2">
        <Badge
          variant="outline"
          className={cn("text-[9px] px-1 py-0 border-0 font-semibold", CATEGORY_COLORS[alert.type.toLowerCase() as DetectionCategory] || "")}
        >
          {CATEGORY_LABELS[alert.type.toLowerCase() as DetectionCategory] || alert.type}
        </Badge>
        {alert.cameraId && (
          <Badge variant="outline" className="text-[9px] px-1 py-0 bg-primary/5 text-primary/80 border-primary/20">
            <Camera className="h-2.5 w-2.5 mr-0.5 inline" />
            {alert.cameraId}
          </Badge>
        )}
        <Badge
          variant="outline"
          className={`text-[9px] px-1 py-0 font-bold border ${
            alert.cameraId.startsWith("EXAMPLE-")
              ? "bg-amber-500/20 text-amber-400 border-amber-500/30"
              : "bg-red-500/20 text-red-400 border-red-500/30"
          }`}
        >
          {alert.cameraId.startsWith("EXAMPLE-") ? "DEMO" : "LIVE"}
        </Badge>
      </div>

      {/* Info grid */}
      <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-[10px] text-muted-foreground bg-background/30 rounded-md p-2 border border-border/30">
        <div className="flex items-center gap-1">
          <MapPin className="h-2.5 w-2.5 text-danger/60" />
          <span>{alert.location}</span>
        </div>
        <div className="flex items-center gap-1 justify-end">
          <span className="text-[9px] text-muted-foreground/50 uppercase">Conf</span>
          <span className={cn("font-mono font-bold", alert.severity === "critical" ? "text-danger" : "text-warning")}>
            {(alert.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>
    </button>
  )
}

export const AlertFeed = memo(function AlertFeed({
  alerts,
  selectedAlertId,
  onSelectAlert,
  selectedCategories,
  onCategoryChange,
  categoryCounts,
}: AlertFeedProps) {
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center gap-3 border-b border-border/60 px-4 py-3 relative overflow-hidden">
        <div className="absolute inset-0 bg-dot-grid opacity-20 pointer-events-none" />

        <div className="relative flex h-8 w-8 items-center justify-center rounded-xl bg-danger/10 text-danger border border-danger/20">
          <div className="absolute inset-0 bg-danger/15 rounded-xl blur-lg animate-ambient-pulse" />
          <Bell className="h-4 w-4 relative z-10" />
          {alerts.length > 0 && (
            <span className="absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-danger opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-danger border-2 border-background" />
            </span>
          )}
        </div>
        <div>
          <h2 className="text-sm font-bold tracking-tight">Live Incident Feed</h2>
          <p className="text-[10px] text-muted-foreground">Real-time threat alerts</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <span className="absolute inset-0 bg-danger/20 rounded-full blur-md animate-ambient-pulse" />
            <Badge variant="outline" className="font-mono text-xs border-danger/30 text-danger bg-danger/5 glow-danger">
              {alerts.length}
            </Badge>
          </div>
        </div>
      </div>

      <CategoryFilter
        selectedCategories={selectedCategories}
        onCategoryChange={onCategoryChange}
        categoryCounts={categoryCounts}
      />

      {/* Scrollable list */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-2.5 space-y-2">
        {alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <div className="relative">
              <div className="absolute inset-0 bg-primary/10 rounded-full blur-2xl animate-ambient-pulse" />
              <ShieldAlert className="h-12 w-12 text-muted-foreground/30 relative z-10" />
            </div>
            <p className="text-xs font-semibold text-muted-foreground/60 tracking-wide uppercase">Monitoring Active</p>
            <div className="w-24 h-1 bg-secondary rounded-full overflow-hidden">
              <div className="h-full bg-primary/40 animate-shimmer rounded-full" style={{ width: "40%" }} />
            </div>
          </div>
        ) : (
          alerts.map((alert, index) => (
            <AlertItem
              key={alert.id}
              alert={alert}
              isSelected={alert.id === selectedAlertId}
              index={index}
              onSelect={onSelectAlert}
            />
          ))
        )}
      </div>
    </div>
  )
})
