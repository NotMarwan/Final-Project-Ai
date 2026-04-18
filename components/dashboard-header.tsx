"use client"

import { Shield, Camera, AlertTriangle, Wifi, WifiOff, Eye, EyeOff, ScanFace } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"

interface DashboardHeaderProps {
  privacyMode: boolean
  onPrivacyToggle: (value: boolean) => void
  sseConnected: boolean
  totalAlerts: number
  onFacePolicyClick?: () => void
  facePolicySynced: boolean
  facePolicySyncAgeSec: number | null
  facePolicy: {
    identityLabelingEnabled: boolean
    recognitionAuditEnabled: boolean
    recognitionAuditCooldownSec: number
  }
}

export function DashboardHeader({ privacyMode, onPrivacyToggle, sseConnected, totalAlerts, onFacePolicyClick, facePolicySynced, facePolicySyncAgeSec, facePolicy }: DashboardHeaderProps) {
  const facePolicyVariant: "success" | "info" | "danger" = !facePolicySynced
    ? "danger"
    : facePolicy.identityLabelingEnabled && facePolicy.recognitionAuditEnabled
      ? "success"
      : "danger"
  const syncTier = !facePolicySynced
    ? "LOST"
    : facePolicySyncAgeSec === null
      ? "--"
      : facePolicySyncAgeSec < 10
        ? "<10s"
        : facePolicySyncAgeSec < 60
          ? "<1m"
          : ">1m"
  const facePolicyValue = !facePolicySynced
    ? "SYNC:LOST | RETRY"
    : `SYNC:${syncTier} | ID:${facePolicy.identityLabelingEnabled ? "ON" : "MASK"} | AUD:${facePolicy.recognitionAuditEnabled ? "ON" : "OFF"} | CD:${facePolicy.recognitionAuditCooldownSec}s`

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
          <StatusIndicator
            icon={<ScanFace className="h-3.5 w-3.5" />}
            label="Face Policy"
            value={facePolicyValue}
            variant={facePolicyVariant}
            onClick={onFacePolicyClick}
          />
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

function StatusIndicator({
  icon,
  label,
  value,
  variant,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  value?: string
  variant: "success" | "info" | "danger"
  onClick?: () => void
}) {
  const dotColor = { success: "bg-success", info: "bg-primary", danger: "bg-danger" }
  const textColor = { success: "text-success", info: "text-primary", danger: "text-danger" }
  const clickable = typeof onClick === "function"
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-2 rounded-md px-1.5 py-1 transition-colors",
        clickable ? "cursor-pointer hover:bg-secondary/60" : "cursor-default",
      )}
      title={clickable ? "Open Face Policy Controls | افتح إعدادات سياسة الوجوه" : undefined}
    >
      <span className="relative flex h-2 w-2 flex-shrink-0">
        <span className={cn("absolute inline-flex h-full w-full rounded-full opacity-75", dotColor[variant], variant === "danger" ? "animate-ping" : "animate-none")} />
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", dotColor[variant])} />
      </span>
      <span className={cn("text-xs font-medium", textColor[variant])}>{icon}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
      {value !== undefined && <Badge variant="secondary" className="h-5 bg-secondary px-1.5 font-mono text-[10px] text-secondary-foreground">{value}</Badge>}
    </button>
  )
}
