"use client"

import { memo } from "react"
import { ShieldAlert } from "lucide-react"

type Props = {
  hasViolence: boolean
  hasWeapon: boolean
  isMultiThreat: boolean
  violenceScore: number
  weaponScore: number
  severity: "low" | "medium" | "high" | "critical"
  weaponType?: "gun" | "knife" | "explosive" | "unknown"
  cameraId: string
}

const WEAPON_LABEL: Record<NonNullable<Props["weaponType"]>, string> = { gun: "سلاح ناري", knife: "أداة حادة", explosive: "مادة متفجرة", unknown: "سلاح" }

export const MultiThreatBanner = memo(function MultiThreatBanner({ hasViolence, hasWeapon, isMultiThreat, severity, weaponType, cameraId }: Props) {
  if (!hasViolence && !hasWeapon) return null
  const title = isMultiThreat ? "تأكيد اعتداء وسلاح" : hasWeapon ? `تأكيد رصد ${weaponType ? WEAPON_LABEL[weaponType] : "سلاح"}` : "تأكيد رصد اعتداء"
  const critical = severity === "critical"
  const tone = critical ? "var(--threat-critical)" : severity === "high" ? "var(--threat-high)" : "var(--threat-medium)"
  return <div className="pointer-events-none absolute inset-x-0 top-3 z-30 flex justify-center px-3" aria-live={critical ? "assertive" : "polite"} aria-atomic="true">
    <div className="flex max-w-full items-center gap-2.5 rounded-md border bg-[var(--surface-1)]/95 px-3 py-2 backdrop-blur-md" style={{ color: tone, borderColor: tone, boxShadow: critical ? "var(--glow-critical)" : undefined }}>
      <span className={`size-2 flex-none rounded-full bg-current ${critical ? "animate-pulse" : ""}`} aria-hidden="true" /><ShieldAlert size={17} className="flex-none" aria-hidden="true" /><strong className="truncate text-xs">{title}</strong><span className="h-4 w-px flex-none bg-[var(--border-hairline)]" /><bdi className="instrument-num flex-none text-[10px]" dir="ltr">{cameraId}</bdi>
    </div>
  </div>
})
