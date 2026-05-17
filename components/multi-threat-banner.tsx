"use client"

import { memo } from "react"
import { ShieldAlert, AlertTriangle, Crosshair } from "lucide-react"
import { cn } from "@/lib/utils"

interface MultiThreatBannerProps {
  hasViolence: boolean
  hasWeapon: boolean
  isMultiThreat: boolean
  violenceScore: number
  weaponScore: number
  severity: "low" | "medium" | "high" | "critical"
  weaponType?: "gun" | "knife" | "explosive" | "unknown"
  cameraId: string
}

function getBannerText(props: MultiThreatBannerProps): string {
  const vPct = props.violenceScore.toFixed(1)
  const wPct = props.weaponScore.toFixed(1)
  if (props.isMultiThreat) {
    const wLabel = props.weaponType === "gun" ? "GUN" : props.weaponType === "knife" ? "KNIFE" : "WEAPON"
    return `CRITICAL: VIOLENCE + ${wLabel} — ${vPct}% / ${wPct}%`
  }
  if (props.hasWeapon) {
    const wLabel = props.weaponType === "gun" ? "GUN" : props.weaponType === "knife" ? "KNIFE" : "WEAPON"
    return `${wLabel} DETECTED — ${wPct}%`
  }
  return `VIOLENCE DETECTED — ${vPct}%`
}

function getBannerIcon(props: MultiThreatBannerProps) {
  if (props.isMultiThreat) return ShieldAlert
  if (props.hasWeapon) {
    if (props.weaponType === "gun") return Crosshair
    if (props.weaponType === "knife") return Crosshair
    return Crosshair
  }
  return AlertTriangle
}

function getBannerColors(props: MultiThreatBannerProps) {
  if (props.isMultiThreat || props.hasViolence) {
    return {
      border: "border-red-500/60",
      bg: "bg-gradient-to-r from-red-900/80 via-red-800/70 to-red-900/80",
      shadow: "shadow-[0_0_24px_rgba(239,68,68,0.4)]",
    }
  }
  return {
    border: "border-orange-500/60",
    bg: "bg-gradient-to-r from-orange-900/80 via-orange-800/70 to-orange-900/80",
    shadow: "shadow-[0_0_24px_rgba(245,158,11,0.4)]",
  }
}

export const MultiThreatBanner = memo(function MultiThreatBanner(props: MultiThreatBannerProps) {
  if (!props.hasViolence && !props.hasWeapon) return null

  const text = getBannerText(props)
  const Icon = getBannerIcon(props)
  const colors = getBannerColors(props)

  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-30 flex items-center justify-center pt-3 animate-alert-enter">
      <div className={cn("flex items-center gap-3 rounded-lg border px-5 py-2.5 backdrop-blur-sm", colors.border, colors.bg, colors.shadow)}>
        <div className="relative">
          <span className="absolute inset-0 bg-white/20 rounded-full blur-md animate-ambient-pulse" />
          <span className="relative flex h-3 w-3 bg-white rounded-full animate-ping" />
        </div>
        <Icon className="h-5 w-5 text-white" />
        <span className="font-mono text-sm font-black uppercase tracking-wider drop-shadow-lg text-white">
          {text}
        </span>
        <div className="relative">
          <span className="absolute inset-0 bg-white/20 rounded-full blur-md animate-ambient-pulse" />
          <span className="relative flex h-3 w-3 bg-white rounded-full animate-ping" />
        </div>
      </div>
    </div>
  )
})