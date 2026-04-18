"use client"

import { Shield, Camera, AlertTriangle, Wifi, WifiOff, Eye, EyeOff } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

interface DashboardHeaderProps {
  privacyMode: boolean
  onPrivacyToggle: (value: boolean) => void
  sseConnected: boolean
  totalAlerts: number
}

export function DashboardHeader({ privacyMode, onPrivacyToggle, sseConnected, totalAlerts }: DashboardHeaderProps) {
  return (
    <header className="glass flex items-center justify-between px-6 py-3">
      <div className="flex items-center gap-3">
        <Shield className="h-7 w-7 text-primary" />
        <div>
          <h1 className="text-lg font-bold tracking-tight text-foreground">SentinelEye</h1>
          <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Intelligent Surveillance</p>
        </div>
      </div>
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-4">
          <StatusIndicator icon={sseConnected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />} label={sseConnected ? "System Online" : "Reconnecting..."} variant={sseConnected ? "success" : "danger"} />
          <StatusIndicator icon={<Camera className="h-3.5 w-3.5" />} label="Active Cameras" value="3" variant="info" />
          <StatusIndicator icon={<AlertTriangle className="h-3.5 w-3.5" />} label="Alerts This Session" value={String(totalAlerts)} variant={totalAlerts > 0 ? "danger" : "info"} />
        </div>
        <div className="h-6 w-px bg-border" />
        <div className="flex items-center gap-2">
          {privacyMode ? <EyeOff className="h-4 w-4 text-muted-foreground" /> : <Eye className="h-4 w-4 text-muted-foreground" />}
          <span className="text-xs text-muted-foreground">Privacy</span>
          <Switch checked={privacyMode} onCheckedChange={onPrivacyToggle} />
        </div>
      </div>
    </header>
  )
}

function StatusIndicator({ icon, label, value, variant }: { icon: React.ReactNode, label: string, value?: string, variant: "success" | "info" | "danger" }) {
  const dotColor = { success: "bg-success", info: "bg-primary", danger: "bg-danger" }
  const textColor = { success: "text-success", info: "text-primary", danger: "text-danger" }
  return (
    <div className="flex items-center gap-2">
      <span className="relative flex h-2 w-2 flex-shrink-0">
        <span className={cn("absolute inline-flex h-full w-full rounded-full opacity-75", dotColor[variant], variant === "danger" ? "animate-ping" : "animate-none")} />
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", dotColor[variant])} />
      </span>
      <span className={cn("text-xs font-medium", textColor[variant])}>{icon}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
      {value !== undefined && <Badge variant="secondary" className="h-5 bg-secondary px-1.5 font-mono text-[10px] text-secondary-foreground">{value}</Badge>}
    </div>
  )
}
