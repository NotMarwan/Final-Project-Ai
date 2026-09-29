"use client"

import { memo, useEffect, useMemo, useState } from "react"
import { BarChart3, ChevronDown, ChevronUp, Clock3, Download, Search, ShieldAlert, X } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"
import { downloadApiFile } from "@/lib/api-auth"
import { CATEGORY_LABELS, formatAlertRelativeArabic, minuteHeatBuckets } from "@/lib/detection-types"
import { SEVERITY_LABEL, SEVERITY_TOKEN, TRIAGE_LABEL } from "@/lib/sentinel-selectors"
import { useSentinel } from "@/lib/sentinel-store"
import { formatDateTime24, formatTime24 } from "@/components/shell/locale"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

type SortOrder = "newest" | "oldest"

function clipDownloadUrl(path: string): string | null {
  try {
    const base = new URL(API_BASE)
    const url = new URL(path, base)
    return url.origin === base.origin && (url.protocol === "http:" || url.protocol === "https:") ? url.href : null
  } catch { return null }
}

export const AlertHistory = memo(function AlertHistory({ alerts, selectedAlertId, onSelectAlert, compact = false, privacyMode = false }: {
  alerts: LiveAlert[]
  selectedAlertId: string | null
  onSelectAlert: (alert: LiveAlert) => void
  compact?: boolean
  privacyMode?: boolean
}) {
  const [search, setSearch] = useState("")
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest")
  const [showStats, setShowStats] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const { triage } = useSentinel()
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(timer)
  }, [])
  const filtered = useMemo(() => alerts.filter((alert) => {
    const query = search.trim().toLocaleLowerCase("ar")
    return !query || [alert.id, alert.cameraId, alert.location].some((value) => value.toLocaleLowerCase("ar").includes(query))
  }).sort((a, b) => (Date.parse(b.isoTime) - Date.parse(a.isoTime)) * (sortOrder === "newest" ? 1 : -1)), [alerts, search, sortOrder])
  const buckets = minuteHeatBuckets(alerts, now, 30)
  const maxBucket = Math.max(1, ...buckets.map((bucket) => bucket.total))
  const stats = {
    total: alerts.length,
    critical: alerts.filter((alert) => alert.severity === "critical").length,
    high: alerts.filter((alert) => alert.severity === "high").length,
    medium: alerts.filter((alert) => alert.severity === "medium").length,
  }

  if (compact) return <section aria-label="توزيع التنبيهات خلال آخر 30 دقيقة" className="shrink-0 border-t border-[var(--border-hairline)] bg-[var(--surface-1)] px-4 py-3">
    <div className="mb-2 flex items-center justify-between gap-2 text-[10px]"><span className="flex items-center gap-1.5 font-semibold text-[var(--text-secondary)]"><BarChart3 size={13} className="text-[var(--signal)]" />توزيع الاستلام · آخر 30 دقيقة</span><bdi dir="ltr" className="instrument-num text-[var(--text-secondary)]">{stats.total}</bdi></div>
    <div className="flex h-8 items-end gap-px" role="img" aria-label={`توزيع ${stats.total} تنبيه خلال آخر 30 دقيقة`}>
      {buckets.map((bucket) => <span key={bucket.start} className="flex h-full min-w-0 flex-1 items-end rounded-sm bg-[var(--surface-2)]"><i className="block w-full rounded-sm" style={{ height: bucket.total ? `${Math.max(18, bucket.total / maxBucket * 100)}%` : "2px", background: bucket.critical ? "var(--threat-critical)" : bucket.total ? "var(--signal)" : "var(--border-hairline)" }} /></span>)}
    </div>
    <div className="mt-1 flex justify-between text-[9px] text-[var(--text-tertiary)]"><span>قبل 30 دقيقة</span><span>الآن</span></div>
  </section>

  return <section aria-label="تاريخ التنبيهات" className="flex h-full min-h-0 flex-col bg-[var(--surface-1)]">
    <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--border-hairline)] px-4 py-2.5"><div><div className="flex items-center gap-2"><Clock3 size={14} className="text-[var(--signal)]" /><h2 className="text-[13px] font-bold">سجل الحوادث</h2></div><p className="mt-0.5 text-[10px] text-[var(--text-tertiary)]">توزيع التنبيهات المستلمة خلال آخر 30 دقيقة</p></div><button type="button" aria-expanded={showStats} onClick={() => setShowStats(!showStats)} className="flex min-h-8 items-center gap-1.5 rounded border border-[var(--border-hairline)] px-2 text-[10px] text-[var(--text-secondary)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)]"><BarChart3 size={13} />{showStats ? "إخفاء الأعداد" : "عرض الأعداد"}</button></div>
    <div className="shrink-0 border-b border-[var(--border-hairline)] px-4 py-2.5"><div className="flex h-8 items-end gap-px" role="img" aria-label={`مخطط بالدقيقة لآخر 30 دقيقة، ${buckets.reduce((sum, bucket) => sum + bucket.total, 0)} تنبيه`}>
      {buckets.map((bucket) => <span key={bucket.start} title={`${formatTime24(bucket.start)}: ${bucket.total} تنبيه`} className="flex h-full min-w-0 flex-1 items-end rounded-sm bg-[var(--surface-2)]"><i className="block w-full rounded-sm" style={{ height: bucket.total ? `${Math.max(18, bucket.total / maxBucket * 100)}%` : "2px", background: bucket.critical ? "var(--threat-critical)" : bucket.total ? "var(--signal)" : "var(--border-hairline)" }} /></span>)}
    </div><div className="mt-1 flex justify-between text-[9px] text-[var(--text-tertiary)]"><span>قبل 30 دقيقة</span><span>كل عمود دقيقة</span><span>الآن</span></div></div>
    {showStats && <div className="grid shrink-0 grid-cols-4 border-b border-[var(--border-hairline)] py-2 text-center">{([{ label: "المجموع", count: stats.total, color: "var(--text-primary)" }, { label: SEVERITY_LABEL.critical, count: stats.critical, color: SEVERITY_TOKEN.critical }, { label: SEVERITY_LABEL.high, count: stats.high, color: SEVERITY_TOKEN.high }, { label: SEVERITY_LABEL.medium, count: stats.medium, color: SEVERITY_TOKEN.medium }]).map((item) => <div key={item.label} className="border-e border-[var(--border-hairline)] last:border-e-0"><bdi className="instrument-num block text-[14px] font-semibold" style={{ color: item.color }}>{item.count}</bdi><span className="text-[9px] text-[var(--text-tertiary)]">{item.label}</span></div>)}</div>}
    <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-[var(--border-hairline)] px-4 py-2"><div className="relative min-w-36 flex-1"><Search size={13} className="absolute start-2 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" /><input value={search} onChange={(event) => setSearch(event.target.value)} aria-label="بحث في سجل الحوادث" placeholder="بحث بالكاميرا أو الموقع أو المعرّف" className="h-8 w-full rounded border border-[var(--border-hairline)] bg-[var(--surface-2)] ps-7 pe-7 text-[10px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]" />{search && <button type="button" onClick={() => setSearch("")} aria-label="مسح البحث" className="absolute end-1 top-1/2 grid size-6 -translate-y-1/2 place-items-center text-[var(--text-tertiary)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><X size={12} /></button>}</div><div className="flex gap-1" role="group" aria-label="ترتيب السجل"><button type="button" aria-pressed={sortOrder === "newest"} onClick={() => setSortOrder("newest")} className={`min-h-8 rounded px-2 text-[10px] focus-visible:outline-2 focus-visible:outline-[var(--signal)] ${sortOrder === "newest" ? "bg-[var(--surface-3)] text-[var(--signal)]" : "text-[var(--text-secondary)]"}`}>الأحدث</button><button type="button" aria-pressed={sortOrder === "oldest"} onClick={() => setSortOrder("oldest")} className={`min-h-8 rounded px-2 text-[10px] focus-visible:outline-2 focus-visible:outline-[var(--signal)] ${sortOrder === "oldest" ? "bg-[var(--surface-3)] text-[var(--signal)]" : "text-[var(--text-secondary)]"}`}>الأقدم</button></div></div>
    <div className="min-h-0 flex-1 overflow-y-auto">{filtered.length === 0 ? <div className="flex min-h-20 items-center justify-center gap-2 px-4 text-[11px] text-[var(--text-tertiary)]"><ShieldAlert size={15} />{search ? "لا نتائج لهذا البحث" : "لا توجد تنبيهات مستلمة ضمن التصفية"}</div> : filtered.map((alert) => {
      const selected = alert.id === selectedAlertId
      const expanded = alert.id === expandedId
      const color = SEVERITY_TOKEN[alert.severity]
      const clipUrl = alert.clipUrl ? clipDownloadUrl(alert.clipUrl) : null
      return <div key={alert.id} className={`border-b border-[var(--border-hairline)] ${selected ? "bg-[var(--surface-3)]" : "hover:bg-[var(--surface-2)]"}`}>
        <div className="flex items-center gap-2 px-4"><span className="size-1.5 shrink-0 rounded-full" style={{ background: color }} /><button type="button" onClick={() => onSelectAlert(alert)} className="flex min-h-10 min-w-0 flex-1 items-center gap-2 text-start focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><span className="min-w-0 flex-1 truncate text-[11px] text-[var(--text-primary)]">{CATEGORY_LABELS[alert.type.toLowerCase() as "weapon" | "violence"]} · {alert.location}</span><bdi className="instrument-num text-[10px] text-[var(--text-secondary)]" dir="ltr">{alert.cameraId}</bdi><time className="whitespace-nowrap text-[10px] text-[var(--text-tertiary)]" dateTime={alert.isoTime}>{formatAlertRelativeArabic(alert.isoTime, now)}</time></button><button type="button" aria-expanded={expanded} aria-label={`${expanded ? "إخفاء" : "عرض"} تفاصيل ${alert.id}`} onClick={() => setExpandedId(expanded ? null : alert.id)} className="grid size-8 shrink-0 place-items-center rounded text-[var(--text-secondary)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]">{expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}</button></div>
        {expanded && <div className="grid gap-1.5 border-t border-[var(--border-hairline)] bg-[var(--surface-2)] px-4 py-3 text-[10px] text-[var(--text-secondary)] sm:grid-cols-2"><div>حالة المعالجة: {TRIAGE_LABEL[triage[alert.id]?.state ?? "new"]}{triage[alert.id] ? triage[alert.id].source === "server" ? "" : " (الجلسة)" : ""}</div><div>المعرّف: <bdi className="instrument-num" dir="ltr">{alert.id}</bdi></div><div>وقت الاستلام: <time dateTime={alert.isoTime}>{formatDateTime24(alert.isoTime)}</time></div>{alert.fusionScore !== undefined && <div>درجة الدمج: <bdi className="instrument-num" dir="ltr">{alert.fusionScore.toFixed(1)}%</bdi></div>}{alert.motionScore !== undefined && <div>درجة الحركة: <bdi className="instrument-num" dir="ltr">{alert.motionScore.toFixed(1)}%</bdi></div>}{alert.weaponScore !== undefined && <div>درجة السلاح: <bdi className="instrument-num" dir="ltr">{alert.weaponScore.toFixed(1)}%</bdi></div>}{alert.threatConfidence !== undefined && <div>درجة التهديد (غير معايرة): <bdi className="instrument-num" dir="ltr">{alert.threatConfidence.toFixed(1)}%</bdi></div>}{alert.personCount !== undefined && <div>عدد الأشخاص: <bdi className="instrument-num" dir="ltr">{alert.personCount}</bdi></div>}{alert.fusionModel && <div>النموذج: <bdi dir="ltr">{alert.fusionModel}</bdi></div>}{alert.weaponLabels && alert.weaponLabels.length > 0 && <div>تصنيفات السلاح: {alert.weaponLabels.join("، ")}</div>}{alert.fusionReason && <p className="sm:col-span-2">سبب الدمج: {alert.fusionReason}</p>}{alert.clipUrl && !privacyMode && <div className="sm:col-span-2">{clipUrl ? <button type="button" onClick={() => { setDownloadError(null); void downloadApiFile(clipUrl, `${alert.id.replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 80) || "alert"}.mp4`).catch(() => setDownloadError(alert.id)) }} className="flex min-h-8 items-center gap-1 text-[var(--signal)] underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><Download size={13} />تنزيل المقطع بصلاحية الجلسة</button> : <span>رابط المقطع غير صالح</span>}</div>}{downloadError === alert.id && <p role="alert" className="text-[var(--threat-critical)] sm:col-span-2">تعذر تنزيل المقطع. تحقق من الاتصال والصلاحية.</p>}</div>}
      </div>
    })}</div>
    <div className="shrink-0 border-t border-[var(--border-hairline)] px-4 py-1.5 text-[10px] text-[var(--text-tertiary)]">عرض <bdi className="instrument-num">{filtered.length}</bdi> من <bdi className="instrument-num">{alerts.length}</bdi> تنبيه مستلم</div>
  </section>
})
