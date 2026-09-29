"use client"

import { useEffect, useState } from "react"
import { useTheme } from "next-themes"
import { Eye, EyeOff, Moon, Search, Sun } from "lucide-react"
import type { ConnectionStatus } from "@/lib/sentinel-store"

function UtcClock() {
  const [time, setTime] = useState("--:--:--")
  useEffect(() => {
    const update = () => setTime(new Date().toISOString().slice(11, 19))
    update()
    const timer = setInterval(update, 1000)
    return () => clearInterval(timer)
  }, [])
  return <span className="instrument-num" dir="ltr"><bdi>{time}</bdi> <small>UTC</small></span>
}

export function DashboardHeader({
  connectionStatus, threat, privacyMode, onPrivacyToggle, onOpenPalette, fixtureMode, sectionLabel,
}: {
  connectionStatus: ConnectionStatus
  threat: "critical" | "high" | "calm"
  privacyMode: boolean
  onPrivacyToggle: () => void
  onOpenPalette: () => void
  fixtureMode: boolean
  sectionLabel: string
}) {
  const { resolvedTheme, setTheme } = useTheme()
  const connectionText = connectionStatus === "online" ? "قناة التنبيهات متصلة" : connectionStatus === "reconnecting" ? "إعادة الاتصال" : "قناة التنبيهات غير متصلة"
  const threatText = threat === "critical" ? "تنبيه حرج حديث" : threat === "high" ? "تنبيه مرتفع حديث" : "لا تنبيهات حرجة حديثة"
  return <header className="command-topbar">
    <div className="topbar-location"><span className="topbar-kicker">مركز العمليات /</span><strong>{sectionLabel}</strong></div>
    <div className="topbar-status">
      <span className={`connection-indicator status-${connectionStatus}`}><i />{connectionText}</span>
      <span className={`threat-chip threat-${threat}`}>{threatText}</span>
      {fixtureMode && <span className="fixture-flag">معاينة</span>}
    </div>
    <div className="topbar-actions">
      <UtcClock />
      <button className="icon-action" onClick={() => setTheme(resolvedTheme === "light" ? "dark" : "light")} title="تبديل المظهر" aria-label="تبديل المظهر"><Sun size={17} className="theme-sun" /><Moon size={17} className="theme-moon" /></button>
      <button className={`icon-action ${privacyMode ? "is-active" : ""}`} onClick={onPrivacyToggle} title="وضع الخصوصية" aria-label="وضع الخصوصية" aria-pressed={privacyMode}>{privacyMode ? <EyeOff size={17} /> : <Eye size={17} />}</button>
      <button className="palette-trigger" onClick={onOpenPalette} aria-label="فتح لوحة الأوامر"><Search size={15} /><span>بحث وأوامر</span><kbd dir="ltr">⌘ / Ctrl K</kbd></button>
    </div>
  </header>
}
