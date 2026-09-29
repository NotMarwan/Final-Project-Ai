"use client"

import { useEffect, useRef, useState, type ReactNode } from "react"
import { ChevronLeft, ChevronRight, FilterX, ShieldAlert } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"
import type { CrossFilters } from "@/lib/sentinel-selectors"
import type { ConnectionStatus } from "@/lib/sentinel-store"

const SEVERITY_LABEL = { critical: "حرج", high: "مرتفع", medium: "متوسط" }

export function IncidentsSection({ alerts, selectedAlert, onSelectAlert, filters, onFiltersChange, connectionStatus, fixtureMode, lastRealAlert, feed, dossier, related }: {
  alerts: LiveAlert[]
  selectedAlert: LiveAlert | null
  onSelectAlert: (alert: LiveAlert) => void
  filters: CrossFilters
  onFiltersChange: (filters: CrossFilters) => void
  connectionStatus: ConnectionStatus
  fixtureMode: boolean
  lastRealAlert: LiveAlert | null
  feed: ReactNode
  dossier: ReactNode
  related: ReactNode
}) {
  const [cursor, setCursor] = useState({ selectedId: selectedAlert?.id ?? null, index: 0 })
  const [criticalAnnouncement, setCriticalAnnouncement] = useState("")
  const lastAnnouncedId = useRef(lastRealAlert?.id ?? null)
  const queueRef = useRef<HTMLElement>(null)
  const activeIndex = selectedAlert ? alerts.findIndex((alert) => alert.id === selectedAlert.id) : -1
  const cursorIndex = cursor.selectedId === (selectedAlert?.id ?? null) ? cursor.index : Math.max(activeIndex, 0)
  const clampedCursor = Math.min(Math.max(cursorIndex, 0), Math.max(0, alerts.length - 1))
  useEffect(() => {
    if (!lastRealAlert || fixtureMode || lastAnnouncedId.current === lastRealAlert.id) return
    lastAnnouncedId.current = lastRealAlert.id
    if (lastRealAlert.severity === "critical") setCriticalAnnouncement("تنبيه حرج جديد من الكاميرا " + lastRealAlert.cameraId)
  }, [lastRealAlert, fixtureMode])
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.target instanceof HTMLElement && event.target.closest("input, textarea, select, [contenteditable=true], [role=dialog]")) return
      if (event.key === "j" || event.key === "k") {
        if (!alerts.length) return
        event.preventDefault()
        queueRef.current?.focus({ preventScroll: true })
        setCursor({ selectedId: selectedAlert?.id ?? null, index: Math.max(0, Math.min(alerts.length - 1, clampedCursor + (event.key === "j" ? 1 : -1))) })
      } else if (event.key === "Enter" && alerts[clampedCursor] && !(event.target instanceof HTMLElement && event.target.closest("button, a, summary, [role=button]"))) {
        event.preventDefault()
        onSelectAlert(alerts[clampedCursor])
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [alerts, clampedCursor, onSelectAlert, selectedAlert?.id])

  const chips: { key: keyof CrossFilters; label: string }[] = []
  if (filters.cameraId) chips.push({ key: "cameraId", label: filters.cameraId })
  if (filters.type) chips.push({ key: "type", label: filters.type === "Weapon" ? "أسلحة" : "اعتداءات" })
  if (filters.severity) chips.push({ key: "severity", label: SEVERITY_LABEL[filters.severity] })
  if (filters.confidenceBand !== undefined) chips.push({ key: "confidenceBand", label: "الثقة " + String(filters.confidenceBand * 20) + "–" + String(filters.confidenceBand * 20 + 20) + "%" })

  return <div className="flex h-full min-h-0 flex-col overflow-y-auto px-3 pb-4 pt-4 md:px-5">
    <p className="sr-only" aria-live="assertive">{criticalAnnouncement}</p>
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div><div className="eyebrow"><span className="eyebrow-line" />لوحة القيادة / <bdi dir="ltr" className="instrument-num">04</bdi></div><h1 className="mt-1 text-[clamp(24px,2.2vw,32px)] font-bold leading-[1.3] tracking-tight text-[var(--text-primary)]">ملفات الحوادث <span className="font-normal text-[var(--text-secondary)]">والأدلة</span></h1><p className="mt-1 text-xs text-[var(--text-secondary)]">انتقل من التنبيه إلى المقطع ومؤشرات القرار، ثم راجع الأدلة المرتبطة.</p></div>
      <div className="flex items-center gap-2"><span className="rounded border border-[var(--border-hairline)] px-2 py-1 text-[10px] text-[var(--text-secondary)]">{fixtureMode ? "معاينة تجريبية" : connectionStatus === "online" ? "قناة التنبيهات متصلة" : "قناة التنبيهات غير متصلة"}</span><bdi className="instrument-num text-xs text-[var(--signal)]">{alerts.length}</bdi><span className="text-[10px] text-[var(--text-tertiary)]">ضمن التصفية</span></div>
    </div>
    {chips.length > 0 && <div className="mb-3 flex flex-wrap items-center gap-1.5" aria-label="التصفيات النشطة"><span className="me-1 text-[10px] text-[var(--text-tertiary)]">التصفية:</span>{chips.map((chip) => <button key={chip.key} type="button" onClick={() => onFiltersChange({ ...filters, [chip.key]: undefined })} className="inline-flex items-center gap-1 rounded border border-[var(--signal)] px-2 py-1 text-[10px] text-[var(--signal)] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]">{chip.label}<FilterX size={11} /></button>)}<button type="button" onClick={() => onFiltersChange({ range: filters.range })} className="text-[10px] text-[var(--text-tertiary)] underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-[var(--signal)]">مسح الكل</button></div>}
    <div className="grid min-h-0 flex-1 gap-3 lg:h-[calc(100vh-200px)] lg:min-h-[620px] lg:grid-cols-[minmax(245px,0.85fr)_minmax(0,2.05fr)_minmax(225px,0.8fr)]">
      <aside ref={queueRef} tabIndex={-1} className="flex min-h-[240px] max-h-[260px] flex-col overflow-hidden rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] lg:max-h-none lg:min-h-0" aria-label="قائمة الحوادث">
        <div className="border-b border-[var(--border-hairline)] px-3 py-3"><div className="flex items-center justify-between gap-2"><h2 className="flex items-center gap-2 text-xs font-semibold"><ShieldAlert size={15} className="text-[var(--signal)]" />قائمة التنبيهات</h2><span className="text-[10px] text-[var(--text-tertiary)]"><bdi dir="ltr" className="instrument-num">j / k</bdi> ثم <bdi dir="ltr" className="instrument-num">Enter</bdi></span></div>
          {alerts.length > 0 && <div className="mt-2 flex items-center justify-between rounded bg-[var(--surface-2)] px-2 py-1.5 text-[10px]"><span className="min-w-0 truncate text-[var(--text-secondary)]">مؤشر لوحة المفاتيح: <bdi className="instrument-num text-[var(--text-primary)]">{alerts[clampedCursor].id}</bdi></span><div className="flex gap-1"><button type="button" onClick={() => setCursor({ selectedId: selectedAlert?.id ?? null, index: Math.max(0, clampedCursor - 1) })} aria-label="التنبيه السابق" className="rounded p-1 text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><ChevronRight size={13} /></button><button type="button" onClick={() => setCursor({ selectedId: selectedAlert?.id ?? null, index: Math.min(alerts.length - 1, clampedCursor + 1) })} aria-label="التنبيه التالي" className="rounded p-1 text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><ChevronLeft size={13} /></button><button type="button" onClick={() => onSelectAlert(alerts[clampedCursor])} className="rounded border border-[var(--border-hairline)] px-1.5 text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]">فتح</button></div></div>}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">{feed}</div>
      </aside>
      <main className="min-h-[520px] min-w-0 overflow-y-auto rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] lg:min-h-0" aria-label="ملف الحادثة المحددة">{dossier}</main>
      <aside className="min-h-[210px] overflow-hidden rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] lg:min-h-0" aria-label="المقاطع المرتبطة">{related}</aside>
    </div>
    {activeIndex === -1 && selectedAlert && <p className="mt-2 text-[10px] text-[var(--text-tertiary)]">الحادثة المفتوحة خارج التصفية الحالية. اختر تنبيهاً من القائمة أو امسح التصفية.</p>}
  </div>
}
