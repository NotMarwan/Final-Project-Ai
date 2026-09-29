"use client"

import { useEffect, type ReactNode } from "react"
import { Activity, BarChart3, Clapperboard, LayoutDashboard, PanelRightClose, PanelRightOpen, Radio, Shield, ShieldAlert, SlidersHorizontal } from "lucide-react"
import { DashboardHeader } from "@/components/dashboard-header"
import { AccessNotice } from "@/components/shell/access-notice"
import type { ConnectionStatus } from "@/lib/sentinel-store"

export const SECTIONS = [
  { id: "overview", label: "نظرة عامة", icon: LayoutDashboard },
  { id: "monitor", label: "المراقبة الحية", icon: Radio },
  { id: "demo-clips", label: "المقاطع التجريبية", icon: Clapperboard },
  { id: "incidents", label: "الحوادث", icon: ShieldAlert },
  { id: "intelligence", label: "التحليل الذكي", icon: Activity },
  { id: "operations", label: "العمليات", icon: BarChart3 },
  { id: "system", label: "النظام", icon: SlidersHorizontal },
] as const
export type Section = typeof SECTIONS[number]["id"]

export function AppShell({ children, section, onSectionChange, collapsed, onCollapsedChange, connectionStatus, threat, privacyMode, onPrivacyToggle, onOpenPalette, fixtureMode }: {
  children: ReactNode
  section: Section
  onSectionChange: (section: Section) => void
  collapsed: boolean
  onCollapsedChange: (collapsed: boolean) => void
  connectionStatus: ConnectionStatus
  threat: "critical" | "high" | "calm"
  privacyMode: boolean
  onPrivacyToggle: () => void
  onOpenPalette: () => void
  fixtureMode: boolean
}) {
  // Signals that event handlers are attached; browser tests wait on it instead of timing guesses.
  useEffect(() => { document.documentElement.dataset.hydrated = "true" }, [])
  return <div className={`command-shell ${collapsed ? "rail-collapsed" : ""}`}>
    <aside className="command-rail" aria-label="التنقل الرئيسي">
      <div className="brand-lockup"><span className="brand-mark"><Shield size={25} strokeWidth={1.5} /></span><div className="brand-copy"><strong>AI Sentinel</strong><span>مركز العمليات الأمنية</span></div></div>
      <div className="rail-group-label">محطات العمل</div>
      <nav className="rail-nav">
        {SECTIONS.map(({ id, label, icon: Icon }, index) => <button key={id} title={label} className={`rail-item ${section === id ? "selected" : ""}`} onClick={() => onSectionChange(id)} aria-current={section === id ? "page" : undefined}>
          <Icon size={18} strokeWidth={1.7} /><span className="rail-label">{label}</span><span className="rail-shortcut instrument-num">{index + 1}</span>
        </button>)}
      </nav>
      <div className="rail-footer"><span className="rail-footer-copy">واجهة مراقبة الحوادث<br /><small>القرار النهائي للمشغّل</small></span><button className="rail-collapse" onClick={() => onCollapsedChange(!collapsed)} aria-label={collapsed ? "توسيع القائمة" : "طي القائمة"}>{collapsed ? <PanelRightOpen size={16} /> : <PanelRightClose size={16} />}</button></div>
    </aside>
    <div className="command-main">
      <DashboardHeader connectionStatus={connectionStatus} threat={threat} privacyMode={privacyMode} onPrivacyToggle={onPrivacyToggle} onOpenPalette={onOpenPalette} fixtureMode={fixtureMode} sectionLabel={SECTIONS.find((item) => item.id === section)?.label ?? "نظرة عامة"} />
      <AccessNotice onOpenSystem={() => onSectionChange("system")} />
      {fixtureMode && <div className="fixture-banner" role="status">بيانات تجريبية للمعاينة — ليست رصداً حقيقياً</div>}
      <main className="command-workspace command-section-enter" key={section}>{children}</main>
    </div>
  </div>
}
