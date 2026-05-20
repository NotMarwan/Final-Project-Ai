"use client"

import { memo, useState, useMemo } from "react"
import {
  Search, Clock, AlertTriangle,
  ChevronDown, ChevronUp, MapPin,
  X, CalendarDays, BarChart3,
  CheckCircle2, AlertCircle, XCircle, Crosshair
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import type { LiveAlert } from "@/components/video-player"

interface AlertHistoryProps {
  alerts: LiveAlert[]
  selectedAlertId: string | null
  onSelectAlert: (alert: LiveAlert) => void
}

type SortOrder = "newest" | "oldest"
type SeverityFilter = "all" | "critical" | "high" | "medium"

const SEVERITY_CONFIG = {
  critical: {
    label: "Critical",
    color: "text-red-400 border-red-500/40 bg-red-500/10",
    dot: "bg-red-500",
    icon: XCircle,
  },
  high: {
    label: "High",
    color: "text-orange-400 border-orange-500/40 bg-orange-500/10",
    dot: "bg-orange-500",
    icon: AlertCircle,
  },
  medium: {
    label: "Medium",
    color: "text-yellow-400 border-yellow-500/40 bg-yellow-500/10",
    dot: "bg-yellow-500",
    icon: AlertTriangle,
  },
} as const

function formatRelativeTime(timestamp: string): string {
  const now = Date.now()
  const then = new Date(timestamp).getTime()
  const diffMs = now - then
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return `${diffSec}s ago`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  return `${diffDay}d ago`
}

function formatDateGroup(timestamp: string): string {
  const d = new Date(timestamp)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return "Today"
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday"
  return d.toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" })
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function formatTime(timestamp: string): string {
  return new Date(timestamp).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

function AlertRow({
  alert,
  isSelected,
  onSelect,
}: {
  alert: LiveAlert
  isSelected: boolean
  onSelect: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const severity = alert.severity ?? "medium"
  const sev = SEVERITY_CONFIG[severity] ?? SEVERITY_CONFIG.medium
  const SevIcon = sev.icon

  return (
    <div
      className={cn(
        "group relative border-b border-border/40 transition-all duration-200 cursor-pointer",
        isSelected ? "bg-primary/5" : "hover:bg-muted/30"
      )}
      onClick={onSelect}
    >
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="flex flex-col items-center gap-1 mt-0.5">
          <div className={cn("h-2 w-2 rounded-full", sev.dot, isSelected && "ring-2 ring-primary ring-offset-1")} />
          <div className="h-full w-px bg-border/40" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <SevIcon className={cn("h-3.5 w-3.5 flex-shrink-0", sev.color.replace("text-", ""))} style={{ color: `hsl(${severity === "critical" ? "0,90%,60%" : severity === "high" ? "30,90%,60%" : "50,90%,60%"})` }} />
            <span className={cn("text-xs font-bold uppercase tracking-wide", sev.color)}>
              {sev.label}
            </span>
            <span className="font-mono text-[10px] text-muted-foreground">{formatRelativeTime(alert.timestamp)}</span>
            {alert.weaponScore !== undefined && alert.weaponScore > 0.3 && (
              <Badge variant="destructive" className="h-4 text-[9px] px-1.5 gap-0.5">
                <Crosshair className="h-2.5 w-2.5" /> Weapon
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="font-mono text-xs font-semibold text-foreground">
              {alert.cameraId}
            </span>
            <span className="text-muted-foreground text-xs flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {alert.location}
            </span>
          </div>

          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-muted-foreground">
              Conf: <span className="font-mono text-primary font-semibold">{alert.confidence.toFixed(1)}%</span>
            </span>
            {alert.threatConfidence !== undefined && (
              <span className="text-[10px] text-muted-foreground">
                Threat: <span className="font-mono text-danger font-semibold">{alert.threatConfidence.toFixed(1)}%</span>
              </span>
            )}
            {alert.personCount !== undefined && (
              <span className="text-[10px] text-muted-foreground">
                Persons: <span className="font-mono text-cyan-400 font-semibold">{alert.personCount}</span>
              </span>
            )}
          </div>
        </div>

        <button
          className="h-6 w-6 rounded flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors"
          onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v) }}
        >
          {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {expanded && (
        <div className="px-8 pb-3 pt-1">
          <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-2">
            {alert.fusionScore !== undefined && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">Fusion Score:</span>
                <span className="font-mono text-primary font-semibold">{(alert.fusionScore * 100).toFixed(1)}%</span>
                {alert.fusionModel && <span className="text-muted-foreground">({alert.fusionModel})</span>}
              </div>
            )}
            {alert.motionScore !== undefined && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">Motion:</span>
                <span className="font-mono">{(alert.motionScore * 100).toFixed(1)}%</span>
              </div>
            )}
            {alert.weaponScore !== undefined && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-muted-foreground">Weapon:</span>
                <span className="font-mono">{(alert.weaponScore * 100).toFixed(1)}%</span>
                {alert.weaponLabels && alert.weaponLabels.length > 0 && (
                  <span className="text-muted-foreground">{alert.weaponLabels.join(", ")}</span>
                )}
              </div>
            )}
            {alert.fusionReason && (
              <p className="text-xs text-muted-foreground italic">{alert.fusionReason}</p>
            )}
            {alert.clipUrl && (
              <div className="flex items-center gap-2 text-xs pt-1">
                <span className="text-muted-foreground">Clip:</span>
                <a href={alert.clipUrl} target="_blank" rel="noopener noreferrer" className="text-primary underline">
                  {alert.clipUrl}
                </a>
              </div>
            )}
            <p className="text-[10px] text-muted-foreground font-mono">
              {alert.timestamp} — {alert.isoTime}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

export const AlertHistory = memo(function AlertHistory({
  alerts,
  selectedAlertId,
  onSelectAlert,
}: AlertHistoryProps) {
  const [search, setSearch] = useState("")
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest")
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all")
  const [showStats, setShowStats] = useState(false)

  const filtered = useMemo(() => {
    let result = [...alerts]

    if (severityFilter !== "all") {
      result = result.filter((a) => a.severity === severityFilter)
    }

    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(
        (a) =>
          a.cameraId.toLowerCase().includes(q) ||
          a.location.toLowerCase().includes(q) ||
          a.id.toLowerCase().includes(q)
      )
    }

    result.sort((a, b) => {
      const ta = new Date(a.timestamp).getTime()
      const tb = new Date(b.timestamp).getTime()
      return sortOrder === "newest" ? tb - ta : ta - tb
    })

    return result
  }, [alerts, search, sortOrder, severityFilter])

  const grouped = useMemo(() => {
    const groups: { date: string; alerts: LiveAlert[] }[] = []
    let currentGroup: { date: string; alerts: LiveAlert[] } | null = null
    for (const alert of filtered) {
      const date = formatDateGroup(alert.timestamp)
      if (!currentGroup || currentGroup.date !== date) {
        currentGroup = { date, alerts: [] }
        groups.push(currentGroup)
      }
      currentGroup.alerts.push(alert)
    }
    return groups
  }, [filtered])

  const stats = useMemo(() => {
    const total = alerts.length
    const critical = alerts.filter((a) => a.severity === "critical").length
    const high = alerts.filter((a) => a.severity === "high").length
    const medium = alerts.filter((a) => a.severity === "medium").length
    return { total, critical, high, medium }
  }, [alerts])

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-border/60 px-4 py-4 relative overflow-hidden">
        <div className="absolute inset-0 bg-dot-grid opacity-20 pointer-events-none" />
        <div className="relative flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
            <CalendarDays className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-sm font-bold tracking-tight">Alert History</h2>
            <p className="text-[10px] text-muted-foreground">Chronological incident timeline</p>
          </div>
          <button
            onClick={() => setShowStats((v) => !v)}
            className={cn(
              "ml-auto flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold transition-colors",
              showStats
                ? "border-primary/40 bg-primary/10 text-primary"
                : "border-border text-muted-foreground hover:border-primary/40"
            )}
          >
            <BarChart3 className="h-3 w-3" />
            Stats
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      {showStats && (
        <div className="flex-shrink-0 grid grid-cols-4 border-b border-border/40 bg-muted/20">
          {[
            { label: "Total", value: stats.total, color: "text-foreground" },
            { label: "Critical", value: stats.critical, color: "text-red-400" },
            { label: "High", value: stats.high, color: "text-orange-400" },
            { label: "Medium", value: stats.medium, color: "text-yellow-400" },
          ].map(({ label, value, color }) => (
            <div key={label} className="flex flex-col items-center py-2 border-r border-border/40 last:border-r-0">
              <span className={cn("font-mono text-lg font-bold", color)}>{value}</span>
              <span className="text-[9px] uppercase tracking-widest text-muted-foreground">{label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Search + Filters */}
      <div className="flex-shrink-0 space-y-2 border-b border-border/40 px-4 py-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search camera, location..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-7 pl-8 pr-8 text-xs bg-muted/30 border-border/60 focus:bg-background"
          />
          {search && (
            <button
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              onClick={() => setSearch("")}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          {(["all", "critical", "high", "medium"] as SeverityFilter[]).map((sev) => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-semibold capitalize transition-colors",
                severityFilter === sev
                  ? sev === "critical"
                    ? "border-red-500/50 bg-red-500/20 text-red-400"
                    : sev === "high"
                    ? "border-orange-500/50 bg-orange-500/20 text-orange-400"
                    : sev === "medium"
                    ? "border-yellow-500/50 bg-yellow-500/20 text-yellow-400"
                    : "border-primary/50 bg-primary/20 text-primary"
                  : "border-border text-muted-foreground hover:border-primary/40"
              )}
            >
              {sev}
            </button>
          ))}

          <div className="ml-auto flex items-center gap-1">
            <span className="text-[9px] text-muted-foreground">Sort:</span>
            <button
              onClick={() => setSortOrder("newest")}
              className={cn(
                "rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors",
                sortOrder === "newest" ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground"
              )}
            >
              Newest
            </button>
            <span className="text-muted-foreground text-[9px]">|</span>
            <button
              onClick={() => setSortOrder("oldest")}
              className={cn(
                "rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors",
                sortOrder === "oldest" ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground"
              )}
            >
              Oldest
            </button>
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-y-auto">
        {grouped.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-8">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
              <CheckCircle2 className="h-6 w-6 text-muted-foreground" />
            </div>
            <div>
              <p className="text-sm font-semibold text-muted-foreground">No alerts found</p>
              <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                {search || severityFilter !== "all"
                  ? "Try adjusting your search or filters"
                  : "Alerts will appear here when threats are detected"}
              </p>
            </div>
          </div>
        ) : (
          <div className="py-2">
            {grouped.map((group) => (
              <div key={group.date}>
                <div className="px-4 py-1.5 bg-muted/30 sticky top-0 z-10">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                    <Clock className="h-3 w-3" />
                    {group.date}
                    <span className="ml-1 font-mono text-primary/60">({group.alerts.length})</span>
                  </span>
                </div>
                {group.alerts.map((alert) => (
                  <AlertRow
                    key={alert.id}
                    alert={alert}
                    isSelected={selectedAlertId === alert.id}
                    onSelect={() => onSelectAlert(alert)}
                  />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer count */}
      <div className="flex-shrink-0 border-t border-border/40 px-4 py-2">
        <p className="text-[10px] text-muted-foreground text-center font-mono">
          Showing {filtered.length} of {alerts.length} alerts
        </p>
      </div>
    </div>
  )
})