"use client"

import { memo } from "react"
import { Camera, MapPinned } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"

interface GeoDashboardProps {
  alert: LiveAlert | null
  alerts: LiveAlert[]
  focusCameraId: string
  onCameraSelect?: (cameraId: string) => void
  fixtureMode?: boolean
  connectionStatus?: string
}

// Positions come from the previous schematic, not surveyed camera coordinates.
const CAMERA_POINTS = [
  { id: "CAM-01", label: "الممر الشمالي", x: 24, y: 27 },
  { id: "CAM-02", label: "البهو", x: 60, y: 58 },
  { id: "CAM-03", label: "المخرج الجنوبي", x: 85, y: 32 },
] as const
const SEVERITY = { critical: { label: "حرج", color: "var(--threat-critical)" }, high: { label: "مرتفع", color: "var(--threat-high)" }, medium: { label: "متوسط", color: "var(--threat-medium)" } } as const

function maxSeverity(alerts: LiveAlert[]) {
  if (alerts.some(alert => alert.severity === "critical")) return "critical"
  if (alerts.some(alert => alert.severity === "high")) return "high"
  if (alerts.some(alert => alert.severity === "medium")) return "medium"
  return null
}

export const GeoDashboard = memo(function GeoDashboard({ alert, alerts, focusCameraId, onCameraSelect, fixtureMode = false, connectionStatus = "offline" }: GeoDashboardProps) {
  const extraCameras = [...new Set(alerts.map(item => item.cameraId))].filter(id => !CAMERA_POINTS.some(point => point.id === id))
  const focused = focusCameraId
  const unavailable = !fixtureMode && connectionStatus !== "online" && alerts.length === 0
  return <section className="overflow-hidden rounded-[var(--radius-panel)] border border-[var(--border-hairline)] bg-[var(--surface-1)]" aria-label="مخطط توزع الحوادث">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-hairline)] px-5 py-4"><div className="flex items-center gap-3"><MapPinned size={19} className="text-[var(--signal)]" /><div><h2 className="text-sm font-semibold">مخطط المناطق</h2><p className="mt-1 text-[10px] text-[var(--text-tertiary)]">مواضع توضيحية · العلامات من تنبيهات الفترة المحددة{alert && <> · الحادثة المحددة <bdi dir="ltr" className="instrument-num">{alert.cameraId}</bdi></>}</p></div></div><span className="rounded border border-[var(--border-hairline)] px-2 py-1 text-[10px] text-[var(--state-offline)]">{fixtureMode ? "عينة للمعاينة" : connectionStatus === "online" ? "تنبيهات الجلسة" : "القناة غير متصلة"}</span></div>
    <div className="p-3 sm:p-5"><div className="relative h-[340px] overflow-hidden rounded-md border border-[var(--border-hairline)] bg-[var(--surface-0)] sm:h-[430px]">
      <div className="pointer-events-none absolute inset-0 opacity-35" style={{ backgroundImage: "linear-gradient(var(--border-hairline) 1px, transparent 1px), linear-gradient(90deg, var(--border-hairline) 1px, transparent 1px)", backgroundSize: "28px 28px" }} />
      <div className="absolute inset-x-4 top-4 z-10 flex items-start justify-between gap-2 text-[10px] text-[var(--text-tertiary)]"><span className="rounded border border-[var(--border-hairline)] bg-[var(--surface-1)] px-2 py-1">مخطط غير جغرافي</span><span className="rounded border border-[var(--border-hairline)] bg-[var(--surface-1)] px-2 py-1">منطقة / <bdi dir="ltr" className="instrument-num">01</bdi></span></div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full" role="img" aria-label="رسم توضيحي للممر الشمالي والبهو والمخرج الجنوبي">
        <path d="M8 13 H92 V84 H8 Z" fill="var(--surface-1)" stroke="var(--border-hairline)" strokeWidth=".5" />
        <path d="M14 20 H37 V42 H14 Z M42 20 H70 V37 H42 Z M75 20 H87 V42 H75 Z M14 48 H36 V76 H14 Z M42 43 H70 V76 H42 Z M75 48 H87 V76 H75 Z" fill="var(--surface-2)" stroke="var(--border-hairline)" strokeWidth=".5" />
        <path d="M8 45 H92 M39 13 V84 M72 13 V84" fill="none" stroke="var(--text-tertiary)" strokeWidth=".35" strokeDasharray="1 1.5" opacity=".55" />
        <path d="M50 84 V94 M47 90 L50 94 L53 90" fill="none" stroke="var(--signal)" strokeWidth=".7" />
      </svg>
      {CAMERA_POINTS.map(point => { const items = alerts.filter(item => item.cameraId === point.id); const severity = maxSeverity(items); const color = severity ? SEVERITY[severity].color : "var(--state-offline)"; const size = Math.min(58, 32 + items.length * 4); const isSelected = focused === point.id; return <button key={point.id} onClick={() => onCameraSelect?.(point.id)} aria-pressed={isSelected} aria-label={point.id + "، " + point.label + "، " + (unavailable ? "لا توجد بيانات" : items.length + " تنبيه") + (severity ? "، أعلى خطورة " + SEVERITY[severity].label : "")} className="absolute z-20 flex flex-col items-center gap-1 rounded-md focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--signal)]" style={{ insetInlineStart: point.x + "%", top: point.y + "%", color, transform: "translate(50%, -50%)" }}><span className="instrument-num grid rounded-full border-2 bg-[var(--surface-0)] text-[12px] font-bold shadow-[var(--shadow-panel)] transition-transform duration-[var(--motion-fast)] hover:scale-110 motion-reduce:transition-none motion-reduce:hover:scale-100" style={{ width: size, height: size, borderColor: color, placeItems: "center", boxShadow: isSelected ? "0 0 0 4px var(--surface-3)" : undefined }}><bdi dir="ltr">{unavailable ? "—" : items.length}</bdi></span><span className="instrument-num rounded bg-[var(--surface-0)] px-1.5 py-0.5 text-[10px] font-semibold"><bdi dir="ltr">{point.id}</bdi></span></button> })}
      {!alerts.length && <div className="absolute inset-x-4 bottom-4 z-10 rounded border border-[var(--border-hairline)] bg-[var(--surface-1)] px-3 py-2 text-center text-xs text-[var(--text-secondary)]">{connectionStatus === "online" ? "لا توجد حوادث ضمن التصفية" : "لا توجد بيانات حوادث متاحة؛ حالة الكاميرات غير معروفة"}</div>}
    </div>
    <div className="mt-4 grid gap-2 sm:grid-cols-3">{CAMERA_POINTS.map(point => { const items = alerts.filter(item => item.cameraId === point.id); const severity = maxSeverity(items); return <button key={point.id} onClick={() => onCameraSelect?.(point.id)} aria-pressed={focused === point.id} className={"flex min-w-0 items-center gap-3 rounded-md border p-3 text-start hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] " + (focused === point.id ? "border-[var(--signal)] bg-[var(--surface-2)]" : "border-[var(--border-hairline)]")}><Camera size={16} style={{ color: severity ? SEVERITY[severity].color : "var(--text-tertiary)" }} /><span className="min-w-0 flex-1"><bdi dir="ltr" className="instrument-num block text-xs">{point.id}</bdi><small className="block truncate text-[10px] text-[var(--text-tertiary)]">{point.label}</small></span><bdi dir="ltr" className="instrument-num text-xs" style={{ color: severity ? SEVERITY[severity].color : "var(--text-tertiary)" }}>{unavailable ? "—" : items.length}</bdi></button> })}</div>
    {extraCameras.length > 0 && <div className="mt-3 border-t border-[var(--border-hairline)] pt-3"><p className="mb-2 text-[10px] text-[var(--text-tertiary)]">مصادر بلا موضع على المخطط</p><div className="flex flex-wrap gap-2">{extraCameras.map(id => <button key={id} onClick={() => onCameraSelect?.(id)} className="rounded border border-[var(--border-hairline)] px-2 py-1 text-xs hover:border-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><bdi dir="ltr" className="instrument-num">{id}</bdi></button>)}</div></div>}
    <div className="mt-4 flex flex-wrap gap-4 border-t border-[var(--border-hairline)] pt-3 text-[10px] text-[var(--text-tertiary)]">{Object.entries(SEVERITY).map(([key, value]) => <span key={key} className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full" style={{ background: value.color }} />{value.label}</span>)}<span>الدائرة الأكبر = تنبيهات أكثر</span></div></div>
  </section>
})
