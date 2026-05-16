"use client"

import { useState, useEffect } from "react"
import { Shield, Camera, AlertTriangle, Wifi, WifiOff, Eye, EyeOff, Clock } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

interface DashboardHeaderProps {
  privacyMode: boolean
  onPrivacyToggle: (value: boolean) => void
  sseConnected: boolean
  totalAlerts: number
  onFacePolicyClick?: () => void
  facePolicySynced?: boolean
  facePolicySyncAgeSec?: number | null
  facePolicy?: {
    identityLabelingEnabled: boolean
    recognitionAuditEnabled: boolean
    recognitionAuditCooldownSec: number
    policyUpdatedAt: string | null
  }
}

function useUTCClock() {
  const [time, setTime] = useState("--:--:--")
  useEffect(() => {
    const update = () => {
      const now = new Date()
      setTime(
        now.toISOString().split("T")[1].split(".")[0] + " UTC"
      )
    }
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [])
  return time
}

export function DashboardHeader({
  privacyMode,
  onPrivacyToggle,
  sseConnected,
  totalAlerts,
}: DashboardHeaderProps) {
  const utcTime = useUTCClock()

  return (
    <header className="glass-strong flex items-center justify-between px-4 md:px-6 py-3 relative overflow-hidden shrink-0">
      {/* Dot grid atmospheric background */}
      <div className="absolute inset-0 bg-dot-grid opacity-40 pointer-events-none" />

      {/* Animated glow line at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent animate-shimmer" />

      {/* LEFT: Logo + Title */}
      <div className="flex items-center gap-3 relative z-10">
        <div className="relative">
          <div className="absolute inset-0 bg-primary/20 rounded-xl blur-xl animate-ambient-pulse" />
          <Shield className="h-8 w-8 text-primary animate-shield-pulse relative z-10" />
        </div>
        <div>
          <h1 className="text-lg md:text-xl font-black tracking-wider text-foreground relative">
            <span className="bg-gradient-to-r from-blue-400 via-blue-300 to-blue-500 bg-clip-text text-transparent">
              SENTINELEYE
            </span>
          </h1>
          <p className="text-[9px] md:text-[10px] uppercase tracking-[0.3em] text-muted-foreground font-medium">
            Intelligent Surveillance Platform
          </p>
        </div>
      </div>

      {/* CENTER: Mission Control Status Strip */}
      <div className="hidden md:flex items-center gap-2 relative z-10">
        <StatusPill
          icon={sseConnected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
          label={sseConnected ? "Online" : "Reconnecting"}
          variant={sseConnected ? "success" : "danger"}
        />
        <div className="h-4 w-px bg-border/50" />
        <StatusPill
          icon={<Camera className="h-3 w-3" />}
          label="Live"
          value="2"
          variant="info"
        />
        <div className="h-4 w-px bg-border/50" />
        <StatusPill
          icon={<AlertTriangle className="h-3 w-3" />}
          label="Alerts"
          value={String(totalAlerts)}
          variant={totalAlerts > 0 ? "danger" : "info"}
          flash={totalAlerts > 0}
        />
      </div>

      {/* RIGHT: Clock + Privacy */}
      <div className="flex items-center gap-3 md:gap-4 relative z-10">
        {/* Live UTC Clock */}
        <div className="hidden sm:flex items-center gap-1.5 rounded-md bg-black/30 border border-white/5 px-2.5 py-1.5">
          <Clock className="h-3 w-3 text-muted-foreground animate-clock-tick" />
          <span className="font-mono text-[11px] text-muted-foreground tracking-wider">{utcTime}</span>
        </div>

        <div className="h-6 w-px bg-gradient-to-b from-transparent via-border to-transparent hidden md:block" />

        <div className="flex items-center gap-2">
          {privacyMode ? <EyeOff className="h-4 w-4 text-muted-foreground" /> : <Eye className="h-4 w-4 text-muted-foreground" />}
          <span className="text-xs text-muted-foreground hidden sm:inline">Privacy</span>
          <Switch checked={privacyMode} onCheckedChange={onPrivacyToggle} />
        </div>
      </div>
    </header>
  )
}

function StatusPill({
  icon,
  label,
  value,
  variant,
  flash = false,
}: {
  icon: React.ReactNode
  label: string
  value?: string
  variant: "success" | "info" | "danger"
  flash?: boolean
}) {
  const dotColor = { success: "bg-success", info: "bg-primary", danger: "bg-danger" }
  const textColor = { success: "text-success", info: "text-primary", danger: "text-danger" }
  const glowClass = { success: "glow-success", info: "glow-primary", danger: "glow-danger" }[variant]

  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-lg px-2.5 py-1.5 transition-all duration-300 bg-white/[0.03] border border-white/[0.06]",
        flash ? "animate-threat-flash" : ""
      )}
    >
      <span className="relative flex h-2 w-2 flex-shrink-0">
        <span
          className={cn(
            "absolute inline-flex h-full w-full rounded-full opacity-70",
            dotColor[variant],
            variant === "danger" ? "animate-ambient-pulse" : "animate-none"
          )}
        />
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", dotColor[variant], glowClass)} />
      </span>
      <span className={cn("text-[10px] font-semibold", textColor[variant])}>{icon}</span>
      <span className="text-[10px] text-muted-foreground font-medium tracking-wide hidden lg:inline">{label}</span>
      {value !== undefined && (
        <Badge className={cn("h-4 bg-secondary/80 px-1.5 font-mono text-[9px] text-secondary-foreground backdrop-blur-sm border border-border/50", glowClass)}>
          {value}
        </Badge>
      )}
    </div>
  )
}
