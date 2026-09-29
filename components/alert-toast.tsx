"use client"

import { useEffect, useRef } from "react"
import { ArrowUpLeft, Crosshair, ShieldAlert, X } from "lucide-react"
import { isToastSuppressedForTab } from "@/lib/live-visual-state"
import { SEVERITY_LABEL, SEVERITY_TOKEN } from "@/lib/sentinel-selectors"
import { useSentinel } from "@/lib/sentinel-store"
import type { LiveAlert } from "@/components/video-player"

interface AlertToastProps {
  /** Newest first. The caller owns the queue; this stack renders the top few. */
  alerts: LiveAlert[]
  activeTab: string
  onNavigate: (alert: LiveAlert) => void
  onDismiss: (alertId: string) => void
  onDismissAll?: () => void
}

const VISIBLE_TOASTS = 3
const AUTO_DISMISS_MS = 6_000

/** Stacked alert notifications. Each card is its own live region: critical
 *  alerts are assertive and persist until reviewed, others are polite and
 *  auto-dismiss (`بعد 6 ثوانٍ`). Reduced motion removes the entry animation. */
export function AlertToast({ alerts, activeTab, onNavigate, onDismiss, onDismissAll }: AlertToastProps) {
  const { fixtureMode } = useSentinel()
  const suppressed = isToastSuppressedForTab(activeTab)
  const dismissRef = useRef(onDismiss)
  const scheduledRef = useRef<Map<string, number>>(new Map())
  useEffect(() => { dismissRef.current = onDismiss }, [onDismiss])

  useEffect(() => {
    if (suppressed) {
      for (const alert of alerts) dismissRef.current(alert.id)
      return
    }
    for (const alert of alerts) {
      if (alert.severity === "critical" || scheduledRef.current.has(alert.id)) continue
      scheduledRef.current.set(alert.id, window.setTimeout(() => {
        scheduledRef.current.delete(alert.id)
        dismissRef.current(alert.id)
      }, AUTO_DISMISS_MS))
    }
  })

  useEffect(() => () => {
    for (const timer of scheduledRef.current.values()) window.clearTimeout(timer)
    scheduledRef.current.clear()
  }, [])

  const visible = alerts.slice(0, VISIBLE_TOASTS)
  const hiddenCount = Math.max(0, alerts.length - visible.length)
  if (suppressed || visible.length === 0) return null

  return <div
    role="region"
    aria-label="التنبيهات الواردة"
    className="fixed start-4 top-4 z-[90] flex w-[min(390px,calc(100vw-2rem))] flex-col gap-2"
    onKeyDown={(event) => { if (event.key === "Escape") onDismiss(visible[0].id) }}
  >
    {visible.map((alert) => <ToastCard key={alert.id} alert={alert} fixtureMode={fixtureMode} onNavigate={() => onNavigate(alert)} onDismiss={() => onDismiss(alert.id)} />)}
    {hiddenCount > 0 && <button type="button" onClick={() => onDismissAll?.()} className="rounded-md border border-[var(--border-hairline)] bg-[var(--surface-1)] px-3 py-1.5 text-[10px] text-[var(--text-secondary)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]">إخفاء {hiddenCount} تنبيهات إضافية</button>}
  </div>
}

function ToastCard({ alert, fixtureMode, onNavigate, onDismiss }: {
  alert: LiveAlert
  fixtureMode: boolean
  onNavigate: () => void
  onDismiss: () => void
}) {
  const critical = alert.severity === "critical"
  const weapon = alert.type === "Weapon"
  const Icon = weapon ? Crosshair : ShieldAlert
  const severityColor = SEVERITY_TOKEN[alert.severity]

  return <div role={critical ? "alert" : "status"} aria-live={critical ? "assertive" : "polite"} aria-atomic="true" className="motion-safe:animate-alert-enter">
    <div className="overflow-hidden rounded-md border bg-[var(--surface-1)] shadow-[var(--shadow-panel)]" style={{ borderColor: severityColor }}>
      <div className="flex items-start gap-3 border-s-4 px-4 py-3.5" style={{ borderInlineStartColor: severityColor }}>
        <div className={`grid size-9 shrink-0 place-items-center rounded bg-[var(--surface-3)] ${critical ? "motion-safe:animate-pulse" : ""}`} style={{ color: severityColor }}><Icon size={20} /></div>
        <div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="text-[10px] font-bold" style={{ color: severityColor }}>تنبيه {SEVERITY_LABEL[alert.severity]}</span><span className="text-[9px] text-[var(--text-tertiary)]">{fixtureMode ? "عينة معاينة" : "مستلم من القناة"}</span></div><h2 className="mt-1 text-[14px] font-bold text-[var(--text-primary)]">{weapon ? "رصد سلاح" : "رصد اعتداء"}</h2><p className="mt-1 text-[11px] text-[var(--text-secondary)]"><bdi className="instrument-num" dir="ltr">{alert.cameraId}</bdi> · {alert.location}</p><p className="mt-1 text-[10px] text-[var(--text-tertiary)]">درجة النموذج <bdi className="instrument-num" dir="ltr">{Math.round(alert.confidence)}/100</bdi> (غير معايرة) · حالة المصدر تحتاج تحققاً مستقلاً</p></div>
        <button type="button" onClick={onDismiss} aria-label={`إغلاق تنبيه ${alert.cameraId}`} className="grid size-8 shrink-0 place-items-center rounded text-[var(--text-secondary)] hover:bg-[var(--surface-3)] hover:text-[var(--text-primary)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><X size={16} /></button>
      </div>
      <div className="flex items-center justify-between border-t border-[var(--border-hairline)] px-4 py-2"><span className="text-[10px] text-[var(--text-tertiary)]">{critical ? "يبقى التنبيه حتى تراجعه أو تغلقه" : "يغلق تلقائياً بعد 6 ثوانٍ"}</span><button type="button" onClick={onNavigate} className="flex min-h-9 items-center gap-1.5 rounded px-2 text-[11px] font-semibold hover:bg-[var(--surface-3)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]" style={{ color: severityColor }}>مراجعة الحادثة<ArrowUpLeft size={13} /></button></div>
    </div>
  </div>
}
