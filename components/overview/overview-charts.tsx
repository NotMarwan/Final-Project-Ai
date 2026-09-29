"use client"

import { useRef, useState } from "react"
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts"
import type { LiveAlert } from "@/components/video-player"
import { ALERT_TYPE_SHORT_LABELS, SEVERITY_LABELS } from "@/lib/detection-types"
import type { AlertTypeKey, SeverityKey } from "@/lib/detection-types"
import { confidenceHistogram, countsByCamera, countsBySeverity } from "@/lib/sentinel-selectors"
import type { CrossFilters } from "@/lib/sentinel-selectors"
import { InstrumentPanel } from "@/components/shell/primitives"
import { formatTime24 } from "@/components/shell/locale"
import { inTimeWindow, makeTimeline, windowForBuckets, type TimeWindow } from "./overview-time"

const TYPE_COLOR: Record<AlertTypeKey, string> = { Weapon: "var(--cat-weapon)", Violence: "var(--cat-violence)" }
const SEVERITY_COLOR: Record<SeverityKey, string> = { critical: "var(--threat-critical)", high: "var(--threat-high)", medium: "var(--threat-medium)" }

type Props = {
  alerts: LiveAlert[]
  timelineAlerts: LiveAlert[]
  cameraAlerts: LiveAlert[]
  severityAlerts: LiveAlert[]
  confidenceAlerts: LiveAlert[]
  filters: CrossFilters
  onFiltersChange: (filters: CrossFilters) => void
  now: number
  selectedWindow: TimeWindow | null
  onWindowChange: (window: TimeWindow | null) => void
  hoveredCamera: string | null
  onHoveredCameraChange: (cameraId: string | null) => void
  hoveredBucket: TimeWindow | null
  onHoveredBucketChange: (bucket: TimeWindow | null) => void
}

/** WAI Complex Images pattern: every chart carries a text summary and a data
 *  table equivalent so the visual is never the only way to read the numbers. */
function ChartDataTable({ caption, headers, rows }: { caption: string; headers: string[]; rows: (string | number)[][] }) {
  return <details className="chart-table-toggle"><summary>جدول البيانات</summary><table><caption>{caption}</caption><thead><tr>{headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => cellIndex === 0 ? <th key={cellIndex} scope="row">{cell}</th> : <td key={cellIndex}><bdi dir="ltr" className="instrument-num">{cell}</bdi></td>)}</tr>)}</tbody></table></details>
}

export function OverviewCharts({ timelineAlerts, cameraAlerts, severityAlerts, confidenceAlerts, filters, onFiltersChange, now, selectedWindow, onWindowChange, hoveredCamera, onHoveredCameraChange, hoveredBucket, onHoveredBucketChange }: Props) {
  const [hoveredType, setHoveredType] = useState<LiveAlert["type"] | null>(null)
  const [dragEnd, setDragEnd] = useState<number | null>(null)
  const dragStart = useRef<number | null>(null)
  const timeline = makeTimeline(timelineAlerts, filters.range, now)
  const bucketCounts = timeline.buckets.map((bucket) => ({
    Weapon: bucket.alerts.filter((alert) => alert.type === "Weapon").length,
    Violence: bucket.alerts.filter((alert) => alert.type === "Violence").length,
  }))
  const maxBucket = Math.max(1, ...timeline.buckets.map((bucket) => bucket.alerts.length))
  const byCamera = countsByCamera(cameraAlerts)
  const cameras = Object.entries(byCamera).sort(([a], [b]) => a.localeCompare(b)).map(([cameraId, count]) => ({
    cameraId, count,
    Weapon: cameraAlerts.filter((alert) => alert.cameraId === cameraId && alert.type === "Weapon").length,
    Violence: cameraAlerts.filter((alert) => alert.cameraId === cameraId && alert.type === "Violence").length,
  }))
  const maxCameraCount = Math.max(1, ...cameras.map((item) => item.count))
  const bySeverity = countsBySeverity(severityAlerts)
  const severity = (["critical", "high", "medium"] as const).map((key) => ({ key, label: SEVERITY_LABELS[key], count: bySeverity[key] ?? 0 })).filter((item) => item.count > 0)
  const confidence = confidenceHistogram(confidenceAlerts)
  const hoveredAlerts = hoveredBucket ? timelineAlerts.filter((alert) => inTimeWindow(alert, hoveredBucket)) : []
  const hoveredSeverities = new Set(hoveredAlerts.map((alert) => alert.severity))
  const hoveredCameras = new Set(hoveredAlerts.map((alert) => alert.cameraId))
  const choose = <K extends keyof CrossFilters>(key: K, value: CrossFilters[K]) => onFiltersChange({ ...filters, [key]: filters[key] === value ? undefined : value })

  const indexAt = (element: HTMLElement, clientX: number) => {
    const rect = element.getBoundingClientRect()
    return Math.max(0, Math.min(timeline.buckets.length - 1, Math.floor((clientX - rect.left) / rect.width * timeline.buckets.length)))
  }
  const hoverIndex = (index: number) => onHoveredBucketChange(timeline.buckets[index])

  // Text alternatives (chart is never the only representation of its numbers).
  const timelineTotal = timeline.buckets.reduce((sum, bucket) => sum + bucket.alerts.length, 0)
  const timelineSummary = `ملخص الرسم: ${timelineTotal} تنبيه موزعة على ${timeline.buckets.length} فترات زمنية متساوية؛ أكبر فترة فيها ${Math.max(0, ...timeline.buckets.map((bucket) => bucket.alerts.length))} تنبيهات. الفترة المحددة: ${selectedWindow ? `${formatTime24(selectedWindow.from)} إلى ${formatTime24(selectedWindow.to)}` : "لا توجد"}.`
  const cameraSummary = `ملخص الرسم: ${cameras.length} كاميرا وردت منها تنبيهات${cameras.length ? `؛ الأعلى ${cameras[0].cameraId} بعدد ${cameras[0].count}` : ""}. الكاميرات بلا تنبيهات غير مدرجة.`
  const severitySummary = `ملخص الرسم: ${severityAlerts.length} تنبيه حسب الخطورة${severity.length ? ` — ${severity.map((item) => `${item.count} ${item.label}`).join("، ")}` : ""}.`
  const confidenceSummary = `ملخص الرسم: درجات ثقة غير معايرة من 0 إلى 100 — ${confidence.map((band) => `${band.label}: ${band.count}`).join("، ")}.`

  return <div className="chart-grid">
    <InstrumentPanel title="تسلسل التنبيهات" index="01" className="timeline-chart">
      <p className="chart-summary" id="timeline-summary">{timelineSummary}</p>
      <div className="chart-legend">{(["Weapon", "Violence"] as const).map((type) => <button key={type} type="button" aria-pressed={filters.type === type} className={filters.type === type ? "is-selected" : ""} onMouseEnter={() => setHoveredType(type)} onMouseLeave={() => setHoveredType(null)} onFocus={() => setHoveredType(type)} onBlur={() => setHoveredType(null)} onClick={() => choose("type", type)}><i style={{ background: TYPE_COLOR[type] }} />{ALERT_TYPE_SHORT_LABELS[type]}</button>)}</div>
      <div className="timeline-plot" dir="ltr" role="group" aria-describedby="timeline-summary" aria-label="أعمدة التنبيهات عبر الزمن">
        <div className="timeline-gridlines" aria-hidden="true"><i /><i /><i /></div>
        <div className="timeline-bars"
          onPointerDown={(event) => { event.preventDefault(); const index = indexAt(event.currentTarget, event.clientX); dragStart.current = index; setDragEnd(index); hoverIndex(index); event.currentTarget.setPointerCapture(event.pointerId) }}
          onPointerMove={(event) => { const index = indexAt(event.currentTarget, event.clientX); if (dragStart.current !== null) setDragEnd((previous) => previous === index ? previous : index); hoverIndex(index) }}
          onPointerUp={(event) => { if (dragStart.current !== null) onWindowChange(windowForBuckets(timeline.buckets, dragStart.current, indexAt(event.currentTarget, event.clientX))); dragStart.current = null; setDragEnd(null); if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId) }}
          onPointerCancel={() => { dragStart.current = null; setDragEnd(null); onHoveredBucketChange(null) }}
          onPointerLeave={() => { if (dragStart.current === null) onHoveredBucketChange(null) }}>
          {timeline.buckets.map((bucket, index) => {
            const counts = bucketCounts[index]
            const isBrushed = dragStart.current !== null && dragEnd !== null && index >= Math.min(dragStart.current, dragEnd) && index <= Math.max(dragStart.current, dragEnd)
            const isSelected = selectedWindow && bucket.from < selectedWindow.to && bucket.to > selectedWindow.from
            const focusedCamera = hoveredCamera ?? filters.cameraId
            const cameraHere = !focusedCamera || bucket.alerts.some((alert) => alert.cameraId === focusedCamera)
            return <button key={index} type="button" className={`timeline-bucket ${isBrushed ? "is-brushing" : ""} ${isSelected ? "is-selected" : ""} ${!cameraHere ? "is-muted" : ""}`} onFocus={() => hoverIndex(index)} onBlur={() => onHoveredBucketChange(null)} onKeyDown={(event) => {
              // Keyboard alternative to drag-to-brush (WCAG 2.5.7): Enter/Space selects a
              // single bucket; Shift+Arrow extends the current selection bucket by bucket.
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault()
                onWindowChange(windowForBuckets(timeline.buckets, index, index))
              } else if (event.shiftKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
                event.preventDefault()
                const anchor = selectedWindow ? timeline.buckets.findIndex((candidate) => candidate.from === selectedWindow.from) : index
                const edge = event.key === "ArrowLeft" ? Math.max(0, index - 1) : Math.min(timeline.buckets.length - 1, index + 1)
                onWindowChange(windowForBuckets(timeline.buckets, anchor >= 0 ? anchor : index, edge))
              }
            }} aria-label={`${formatTime24(bucket.from)} إلى ${formatTime24(bucket.to)}، ${counts.Weapon} أسلحة، ${counts.Violence} اعتداءات. Enter لتحديد الفترة، أو Shift مع سهم لتوسيع التحديد`}>
              <span className="timeline-stack" style={{ height: `${Math.max(2, bucket.alerts.length / maxBucket * 100)}%` }}><i className="timeline-weapon" style={{ flex: counts.Weapon }} /><i className="timeline-violence" style={{ flex: counts.Violence }} /></span>
              <small className="instrument-num">{formatTime24(bucket.to)}</small>
            </button>
          })}
        </div>
      </div>
      <div className="timeline-readout">{hoveredBucket ? <><bdi dir="ltr" className="instrument-num">{formatTime24(hoveredBucket.from)}–{formatTime24(hoveredBucket.to)}</bdi><span>{hoveredAlerts.length} تنبيه · {hoveredCameras.size} كاميرا</span></> : <span>اسحب على الأعمدة لتحديد فترة زمنية</span>}</div>
      <ChartDataTable caption="عدد التنبيهات في كل فترة زمنية" headers={["الفترة", "أسلحة", "اعتداءات"]} rows={timeline.buckets.map((bucket, index) => [`${formatTime24(bucket.from)}–${formatTime24(bucket.to)}`, bucketCounts[index].Weapon, bucketCounts[index].Violence])} />
    </InstrumentPanel>
    <InstrumentPanel title="حسب الكاميرا" index="02" className="camera-chart"><p className="chart-summary" id="camera-summary">{cameraSummary}</p><div className="camera-bars" role="group" aria-describedby="camera-summary">{cameras.map(({ cameraId, count, Weapon, Violence }) => <button key={cameraId} type="button" aria-pressed={filters.cameraId === cameraId} className={`camera-row ${filters.cameraId === cameraId ? "is-selected" : ""} ${hoveredBucket && !hoveredCameras.has(cameraId) ? "is-muted" : ""} ${hoveredCamera === cameraId ? "is-hovered" : ""}`} onMouseEnter={() => onHoveredCameraChange(cameraId)} onMouseLeave={() => onHoveredCameraChange(null)} onFocus={() => onHoveredCameraChange(cameraId)} onBlur={() => onHoveredCameraChange(null)} onClick={() => choose("cameraId", cameraId)} aria-label={`كاميرا ${cameraId}: ${count} تنبيه (${Weapon} أسلحة، ${Violence} اعتداءات)`}><bdi dir="ltr" className="instrument-num">{cameraId}</bdi><span className="camera-bar-track"><i style={{ width: `${Weapon / maxCameraCount * 100}%`, background: TYPE_COLOR.Weapon, opacity: hoveredType && hoveredType !== "Weapon" ? .22 : 1 }} /><i style={{ width: `${Violence / maxCameraCount * 100}%`, background: TYPE_COLOR.Violence, opacity: hoveredType && hoveredType !== "Violence" ? .22 : 1 }} /></span><bdi dir="ltr" className="instrument-num">{count}</bdi></button>)}</div><ChartDataTable caption="عدد التنبيهات حسب الكاميرا" headers={["الكاميرا", "أسلحة", "اعتداءات", "المجموع"]} rows={cameras.map((item) => [item.cameraId, item.Weapon, item.Violence, item.count])} /></InstrumentPanel>
    <InstrumentPanel title="توزيع الخطورة" index="03" className="severity-chart"><p className="chart-summary" id="severity-summary">{severitySummary}</p><div className="severity-layout"><div className="severity-donut" role="img" aria-describedby="severity-summary" aria-label={severitySummary}><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={severity} dataKey="count" nameKey="label" innerRadius="63%" outerRadius="90%" stroke="var(--surface-1)" strokeWidth={3}>{severity.map((item) => <Cell key={item.key} fill={SEVERITY_COLOR[item.key]} fillOpacity={hoveredBucket && !hoveredSeverities.has(item.key) ? .2 : 1} cursor="pointer" onClick={() => choose("severity", item.key)} />)}</Pie></PieChart></ResponsiveContainer><span className="donut-center instrument-num">{severityAlerts.length}<small>تنبيه</small></span></div><div className="severity-legend">{severity.map((item) => <button key={item.key} type="button" aria-pressed={filters.severity === item.key} className={`${filters.severity === item.key ? "is-selected" : ""} ${hoveredBucket && !hoveredSeverities.has(item.key) ? "is-muted" : ""}`} onClick={() => choose("severity", item.key)} aria-label={`تصفية حسب الخطورة ${item.label}: ${item.count} تنبيه`}><i style={{ background: SEVERITY_COLOR[item.key] }} /><span>{item.label}</span><bdi dir="ltr" className="instrument-num">{item.count}</bdi></button>)}</div></div><ChartDataTable caption="توزيع التنبيهات حسب الخطورة" headers={["الخطورة", "العدد"]} rows={severity.map((item) => [item.label, item.count])} /></InstrumentPanel>
    <InstrumentPanel title="توزيع الدرجة" index="04" className="confidence-chart"><p className="chart-summary" id="confidence-summary">{confidenceSummary}</p><div className="chart-caption">درجات الثقة غير المعايرة المبلّغ عنها في التنبيهات (0–100)</div><div className="confidence-bars" role="group" aria-describedby="confidence-summary">{confidence.map((item, index) => <button key={item.label} type="button" aria-pressed={filters.confidenceBand === index} className={`confidence-column ${filters.confidenceBand === index ? "is-selected" : ""}`} onClick={() => choose("confidenceBand", index)} aria-label={`نطاق الدرجة ${item.label}: ${item.count} تنبيه. تصفية حسب النطاق`} title={`${item.label} · ${item.count} تنبيه`}><span className="confidence-bar-slot"><i style={{ height: `${Math.max(3, item.count / Math.max(1, ...confidence.map((band) => band.count)) * 100)}%` }} /></span><small className="instrument-num" dir="ltr">{item.label}</small></button>)}</div><ChartDataTable caption="توزيع درجات الثقة غير المعايرة" headers={["النطاق", "العدد"]} rows={confidence.map((band) => [band.label, band.count])} /></InstrumentPanel>
  </div>
}
