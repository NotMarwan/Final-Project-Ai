"use client"

import dynamic from "next/dynamic"
import { useEffect, useMemo, useRef, useState } from "react"
import type { ReactNode } from "react"
import { ArrowUpLeft, Camera, ChevronLeft, CircleHelp, Crosshair, Radio, ShieldAlert, Timer, X } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"
import type { ConnectionStatus } from "@/lib/sentinel-store"
import { InstrumentValue } from "@/components/shell/primitives"
import { formatTime24 } from "@/components/shell/locale"
import { useNow } from "@/hooks/use-now"
import { ALERT_TYPE_LABELS, ALERT_TYPE_SHORT_LABELS, RANGE_LABELS, SEVERITY_LABELS, STATS_LEGEND } from "@/lib/detection-types"
import type { SeverityKey } from "@/lib/detection-types"
import { SESSION_ALERT_CAP, chartDimensionSets, countsBySeverity, countsByType, latencyPercentiles, previousWindowComparison, selectVisibleAlerts, sessionCoverage, timeBuckets } from "@/lib/sentinel-selectors"
import type { CrossFilters, PreviousWindowComparison, Range } from "@/lib/sentinel-selectors"
import { HeroIncidentInstrument } from "./hero-incident-instrument"
import { inTimeWindow, type TimeWindow } from "./overview-time"
import { useOverviewStats, type StatsSource } from "./use-overview-stats"

const NOW_TICK_MS = 15_000

const OverviewCharts = dynamic(() => import("./overview-charts").then((module) => module.OverviewCharts), {
  ssr: false,
  loading: () => <div className="chart-grid chart-skeletons" role="status" aria-label="جارٍ تجهيز الرسوم البيانية">{["01", "02", "03", "04"].map((index) => <div className="instrument-panel chart-card chart-skeleton" key={index}><div className="chart-skeleton-title" /><div className="chart-skeleton-visual" /><div className="chart-skeleton-axis" /></div>)}</div>,
})

function AnimatedValue({ value }: { value: number }) {
  const [display, setDisplay] = useState(0)
  const previous = useRef(0)
  useEffect(() => {
    const from = previous.current
    previous.current = value
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplay(value)
      return
    }
    const start = performance.now()
    let frame = 0
    const animate = (time: number) => {
      const progress = Math.min(1, (time - start) / 420)
      setDisplay(Math.round(from + (value - from) * (1 - (1 - progress) ** 3)))
      if (progress < 1) frame = requestAnimationFrame(animate)
    }
    frame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(frame)
  }, [value])
  return <bdi className="instrument-num">{display.toLocaleString("en-US")}</bdi>
}

function Sparkline({ values, color = "var(--signal)" }: { values: number[]; color?: string }) {
  const max = Math.max(1, ...values)
  const points = values.map((value, index) => `${index * 100 / Math.max(1, values.length - 1)},${30 - value / max * 23}`).join(" ")
  return <svg className="stat-sparkline" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true"><polyline points={points} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" /></svg>
}

function StatCard({ label, value, icon: Icon, tone, sub, spark, onDrill }: { label: ReactNode; value: number | string; icon: typeof Camera; tone?: string; sub?: string; spark?: number[]; onDrill?: () => void }) {
  const body = <><div className="stat-top"><span>{label}</span><Icon size={16} style={{ color: tone ?? "var(--text-tertiary)" }} /></div><div className="stat-reading">{typeof value === "number" ? <AnimatedValue value={value} /> : <InstrumentValue value={value} />}<i className="stat-change-flash" key={String(value)} aria-hidden="true" /></div><div className="stat-bottom"><span>{sub}</span>{spark && <Sparkline values={spark} color={tone} />}</div></>
  return onDrill
    ? <button type="button" className="overview-stat stat-drill" onClick={onDrill} aria-label={`عرض التنبيهات المطابقة في شاشة الحوادث`}>{body}</button>
    : <div className="overview-stat">{body}</div>
}

function relativeArabic(isoTime: string, now: number) {
  const minutes = Math.max(0, Math.floor((now - Date.parse(isoTime)) / 60_000))
  if (minutes < 1) return "الآن"
  if (minutes < 60) return `قبل ${minutes} د`
  const hours = Math.floor(minutes / 60)
  return hours < 24 ? `قبل ${hours} س` : `قبل ${Math.floor(hours / 24)} ي`
}

function deltaLabel(current: number, comparison: PreviousWindowComparison) {
  if (!comparison.available) {
    return comparison.reason === "all-range" ? "لا توجد فترة مقارنة"
      : comparison.reason === "empty-session" ? "لا توجد تنبيهات في الجلسة"
      : "الفترة السابقة خارج نطاق الجلسة"
  }
  if (comparison.previousCount === 0) return "لا تنبيهات بالفترة السابقة"
  const difference = current - comparison.previousCount
  return `${difference > 0 ? "+" : ""}${difference} عن الفترة السابقة`
}

const FALLBACK_REASON_LABEL: Record<"offline" | "server-error" | "invalid-payload" | "fixture", string> = {
  offline: "سجل الأدلة غير متاح — الخادم غير متصل",
  "server-error": "سجل الأدلة غير متاح — رفض الخادم الطلب",
  "invalid-payload": "سجل الأدلة غير متاح — استجابة غير صالحة",
  fixture: "وضع المعاينة — بيانات محلية",
}

export function Overview({ alerts, filters, onFiltersChange: upstreamFiltersChange, connectionStatus, fixtureMode, onSelectIncident, onOpenMonitor }: {
  alerts: LiveAlert[]
  filters: CrossFilters
  onFiltersChange: (filters: CrossFilters) => void
  connectionStatus: ConnectionStatus
  fixtureMode: boolean
  onSelectIncident: (alert: LiveAlert) => void
  onOpenMonitor: () => void
}) {
  const clock = useNow(NOW_TICK_MS)
  const [customWindow, setCustomWindow] = useState<TimeWindow | null>(null)
  const [hoveredCamera, setHoveredCamera] = useState<string | null>(null)
  const [hoveredBucket, setHoveredBucket] = useState<TimeWindow | null>(null)
  const [sourceOverride, setSourceOverride] = useState<StatsSource | null>(null)
  const onFiltersChange = (next: CrossFilters) => {
    if (next.range !== filters.range || (Object.keys(next).length === 1 && next.range === "1h")) setCustomWindow(null)
    upstreamFiltersChange(next)
  }
  // Alerts stamped after the last tick must still count, so the window end never trails the newest alert.
  const now = useMemo(() => alerts.reduce((latest, alert) => Math.max(latest, Date.parse(alert.isoTime) || 0), clock), [alerts, clock])
  const baseVisible = useMemo(() => selectVisibleAlerts(alerts, filters, now), [alerts, filters, now])
  const heroAlerts = useMemo(() => selectVisibleAlerts(alerts, { ...filters, cameraId: undefined }, now), [alerts, filters, now])
  const visible = useMemo(() => customWindow ? baseVisible.filter((alert) => inTimeWindow(alert, customWindow)) : baseVisible, [baseVisible, customWindow])
  const chartDimensions = useMemo(() => chartDimensionSets(alerts, filters, now, customWindow), [alerts, filters, now, customWindow])
  const severity = useMemo(() => countsBySeverity(visible), [visible])
  const types = useMemo(() => countsByType(visible), [visible])
  const latency = useMemo(() => latencyPercentiles(visible), [visible])
  const timeline = useMemo(() => timeBuckets(visible, filters, now), [visible, filters, now])
  const coverage = useMemo(() => sessionCoverage(alerts), [alerts])
  const comparison = useMemo(() => previousWindowComparison(alerts, filters, now, customWindow), [alerts, filters, now, customWindow])
  const comparisonCritical = useMemo(() => previousWindowComparison(alerts, { ...filters, severity: "critical" }, now, customWindow), [alerts, filters, now, customWindow])
  const comparisonWeapon = useMemo(() => previousWindowComparison(alerts, { ...filters, type: "Weapon" }, now, customWindow), [alerts, filters, now, customWindow])
  const comparisonViolence = useMemo(() => previousWindowComparison(alerts, { ...filters, type: "Violence" }, now, customWindow), [alerts, filters, now, customWindow])
  const criticalTimeline = useMemo(() => timeBuckets(visible.filter((alert) => alert.severity === "critical"), filters, now), [visible, filters, now])
  const recentCritical = alerts.some((alert) => alert.severity === "critical" && Date.parse(alert.isoTime) >= now - 15 * 60_000)
  const recentHigh = alerts.some((alert) => alert.severity === "high" && Date.parse(alert.isoTime) >= now - 15 * 60_000)
  const threat = recentCritical ? "critical" : recentHigh ? "high" : "calm"
  const hasData = visible.length > 0
  const hasContextData = chartDimensions.context.length > 0
  const isOffline = connectionStatus !== "online"
  const unavailable = isOffline && !fixtureMode && alerts.length === 0

  // Window semantics (D8): closed [now-d, now]; "all" spans the observed session.
  const rangeDuration = filters.range === "15m" ? 15 * 60_000 : filters.range === "1h" ? 60 * 60_000 : filters.range === "24h" ? 24 * 60 * 60_000 : null
  const windowFrom = customWindow?.from ?? (rangeDuration === null ? coverage.observedFrom ?? now : now - rangeDuration)
  const windowTo = customWindow?.to ?? now

  const stats = useOverviewStats({ from: windowFrom, to: windowTo, cameraId: filters.cameraId, enabled: !fixtureMode })
  const activeSource: StatsSource = sourceOverride ?? (stats.status === "persisted" ? "persisted" : "session")
  const persisted = activeSource === "persisted" && stats.status === "persisted" ? stats.payload : null
  const scopeNote = persisted
    ? `سجل الأدلة — الفترة ${formatTime24(windowFrom)}–${formatTime24(windowTo)} حسب وقت تسجيل الأدلة${filters.cameraId ? ` · الكاميرا ${filters.cameraId}` : ""}`
    : `نطاق الجلسة${coverage.observedFrom !== null ? ` منذ ${formatTime24(coverage.observedFrom)}` : ""} · الفترة ${formatTime24(windowFrom)}–${formatTime24(windowTo)}${stats.status === "fallback" ? ` · ${FALLBACK_REASON_LABEL[stats.reason]}` : ""}`

  const chips = [
    filters.range !== "1h" && { key: "range", label: RANGE_LABELS[filters.range] },
    filters.cameraId && { key: "cameraId", label: filters.cameraId },
    filters.type && { key: "type", label: ALERT_TYPE_SHORT_LABELS[filters.type] },
    filters.severity && { key: "severity", label: SEVERITY_LABELS[filters.severity as SeverityKey] },
    filters.confidenceBand !== undefined && { key: "confidenceBand", label: `الدرجة ${filters.confidenceBand * 20}–${filters.confidenceBand * 20 + 20}%` },
  ].filter(Boolean) as { key: keyof CrossFilters; label: string }[]
  const spark = timeline.map((bucket) => bucket.Weapon + bucket.Violence)
  const latencySamples = visible.filter((alert) => typeof alert.alertLatencyMs === "number" && Number.isFinite(alert.alertLatencyMs))
  const latencySpark = latencySamples.slice(0, 8).reverse().map((alert) => alert.alertLatencyMs as number)
  const chooseHeroAlert = (alert: LiveAlert, window: TimeWindow) => { setCustomWindow(window); onFiltersChange({ ...filters, cameraId: alert.cameraId }) }

  // Drill-through (S26-4): apply the same CrossFilters and open the first matching
  // alert in the incidents view. The local brush window cannot travel through the
  // CrossFilters contract — a brushed view stays filtered in-page and says so.
  const openInIncidents = (patch: Partial<CrossFilters>) => {
    const next = { ...filters, ...patch }
    const matches = customWindow ? selectVisibleAlerts(alerts, next, now).filter((alert) => inTimeWindow(alert, customWindow)) : selectVisibleAlerts(alerts, next, now)
    upstreamFiltersChange(next)
    if (matches[0]) onSelectIncident(matches[0])
  }

  return <div className="overview-page">
    <div className="overview-heading"><div><div className="eyebrow"><span className="eyebrow-line" />لوحة القيادة / <bdi dir="ltr" className="instrument-num">01</bdi></div><h1>نظرة عامة <span>على الرصد</span></h1><p>صورة موحّدة للتنبيهات الواردة خلال الفترة المحددة. تؤكد حالة القناة الاتصال فقط.</p></div><button className="outline-action" onClick={onOpenMonitor}><Radio size={15} />فتح المراقبة الحية<ArrowUpLeft size={14} /></button></div>

    <section className={`overview-hero hero-${threat} ${isOffline && !fixtureMode ? "hero-offline" : ""}`}>
      <div className="hero-grid" aria-hidden="true" />
      <div className="hero-gauge"><svg viewBox="0 0 180 180" aria-hidden="true"><circle className="gauge-track" cx="90" cy="90" r="68" /><circle className="gauge-ticks" cx="90" cy="90" r="78" /><circle className="gauge-arc gauge-arc-calm" cx="90" cy="90" r="68" /><circle className="gauge-arc gauge-arc-high" cx="90" cy="90" r="68" /><circle className="gauge-arc gauge-arc-critical" cx="90" cy="90" r="68" /></svg><div className="gauge-center"><Crosshair size={24} /><strong>{isOffline && !fixtureMode ? "؟" : threat === "critical" ? "حرج" : threat === "high" ? "مرتفع" : "هادئ"}</strong><small>إشارة آخر 15 دقيقة — بلا تصفية</small></div></div>
      <div className="hero-copy"><span className="hero-kicker"><i />{fixtureMode ? "وضع المعاينة" : isOffline ? "اتصال غير متاح" : "قناة التنبيهات متصلة"}</span><h2>{fixtureMode ? "محاكاة لحركة التنبيهات." : isOffline ? "الرصد المباشر غير متاح حالياً." : recentCritical ? "ورد تنبيه حرج يتطلب المراجعة." : recentHigh ? "ورد تنبيه مرتفع يتطلب الانتباه." : "لا توجد تنبيهات حرجة حديثة."}</h2><p>{fixtureMode ? "الأرقام أدناه من عينة محلية، وليست نتيجة رصد حي." : isOffline ? "تحقق من تشغيل خدمة التحليل والاتصال بها قبل الاعتماد على الحالة المعروضة." : "هذه الحالة مبنية على التنبيهات المستلمة؛ لا تثبت سلامة كل كاميرا أو نموذج."}</p><div className="hero-micro"><span>{isOffline && !fixtureMode ? "حالة التنبيهات غير متاحة" : <><bdi dir="ltr" className="instrument-num">{visible.length}</bdi> تنبيه مستلم ضمن التصفية</>}</span><span className="hero-separator" /><span>{RANGE_LABELS[filters.range]}</span></div></div>
      <HeroIncidentInstrument alerts={isOffline && !fixtureMode ? [] : heroAlerts} now={now} isOffline={isOffline && !fixtureMode} selectedCamera={filters.cameraId} selectedWindow={customWindow} onSelect={chooseHeroAlert} onHoverCamera={setHoveredCamera} />
    </section>

    <div className="overview-toolbar"><div className="toolbar-title"><span className="section-index instrument-num">02</span><strong>مؤشرات الفترة</strong></div><div className="range-control" role="group" aria-label="النطاق الزمني">{(["15m", "1h", "24h", "all"] as const).map((range) => <button key={range} className={filters.range === range ? "active" : ""} onClick={() => onFiltersChange({ ...filters, range })}>{RANGE_LABELS[range as Range]}</button>)}</div></div>
    {(chips.length > 0 || customWindow) && <div className="active-filters"><span>التصفية النشطة</span>{customWindow && <button onClick={() => setCustomWindow(null)}><bdi dir="ltr" className="instrument-num">{formatTime24(customWindow.from)}–{formatTime24(customWindow.to)}</bdi><X size={13} /></button>}{chips.map((chip) => <button key={chip.key} onClick={() => onFiltersChange(chip.key === "range" ? { ...filters, range: "1h" } : { ...filters, [chip.key]: undefined })}>{chip.label}<X size={13} /></button>)}{visible.length > 0 && <button onClick={() => openInIncidents({})}>عرض في الحوادث</button>}<button className="clear-filters" onClick={() => onFiltersChange({ range: "1h" })}>مسح الكل</button>{customWindow && <small className="brush-note">الفترة المحددة بالسحب تُطبَّق هنا فقط ولا تنتقل إلى شاشة الحوادث.</small>}</div>}

    <div className="stats-scope" role="group" aria-label="مصدر المؤشرات ونطاقها">
      <span>مصدر المؤشرات</span>
      <button type="button" aria-pressed={activeSource === "persisted"} disabled={stats.status !== "persisted"} onClick={() => setSourceOverride("persisted")}>سجل الأدلة (مُخزَّن)</button>
      <button type="button" aria-pressed={activeSource === "session"} onClick={() => setSourceOverride("session")}>الجلسة الحالية</button>
      <span className="stats-scope-note">{scopeNote}{coverage.capped && activeSource === "session" ? ` · مفعّل الحد الأقصى (${SESSION_ALERT_CAP} تنبيهًا) — التنبيهات الأقدم خارج النطاق` : ""} · آخر تحديث {formatTime24(now)}</span>
    </div>

    <div className="overview-stats stagger-children">
      {persisted ? <>
        <StatCard label="سجلات الأدلة بالفترة" value={persisted.recordCount} icon={Radio} tone="var(--signal)" sub={persisted.previousWindow ? deltaLabel(persisted.recordCount, { available: true, previousCount: persisted.previousWindow.recordCount, window: { from: 0, to: 0 } }) : "المقارنة غير متاحة"} />
        <StatCard label="حرجة" value={persisted.bySeverity.critical} icon={ShieldAlert} tone="var(--threat-critical)" sub="سجلات أدلة بخطورة حرجة" />
        <StatCard label={<>أسلحة</>} value="غير متاح" icon={Crosshair} tone="var(--cat-weapon)" sub="سجل الأدلة لا يسجّل نوع التنبيه" />
        <StatCard label="اعتداءات" value="غير متاح" icon={ShieldAlert} tone="var(--cat-violence)" sub="سجل الأدلة لا يسجّل نوع التنبيه" />
        <StatCard label={<>زمن احتساب القرار <bdi dir="ltr">p50 / p95</bdi></>} value="غير متاح" icon={Timer} tone="var(--signal)" sub="سجل الأدلة لا يسجّل الزمن" />
        <StatCard label="الكاميرات النشطة" value="غير متاح" icon={Camera} sub="لا ترد حالة المصدر هنا" />
      </> : <>
        <StatCard label="تنبيهات الفترة" value={unavailable ? "—" : visible.length} icon={Radio} tone="var(--signal)" sub={unavailable ? "القناة غير متصلة" : deltaLabel(visible.length, comparison)} spark={hasData ? spark : undefined} onDrill={visible.length > 0 ? () => openInIncidents({}) : undefined} />
        <StatCard label="حرجة" value={unavailable ? "—" : severity.critical ?? 0} icon={ShieldAlert} tone="var(--threat-critical)" sub={unavailable ? "غير معروف" : deltaLabel(severity.critical ?? 0, comparisonCritical)} spark={hasData ? criticalTimeline.map((bucket) => bucket.Weapon + bucket.Violence) : undefined} onDrill={(severity.critical ?? 0) > 0 ? () => openInIncidents({ severity: "critical" }) : undefined} />
        <StatCard label={ALERT_TYPE_SHORT_LABELS.Weapon} value={unavailable ? "—" : types.Weapon ?? 0} icon={Crosshair} tone="var(--cat-weapon)" sub={unavailable ? "غير معروف" : deltaLabel(types.Weapon ?? 0, comparisonWeapon)} spark={hasData ? timeline.map((bucket) => bucket.Weapon) : undefined} onDrill={(types.Weapon ?? 0) > 0 ? () => openInIncidents({ type: "Weapon" }) : undefined} />
        <StatCard label={ALERT_TYPE_SHORT_LABELS.Violence} value={unavailable ? "—" : types.Violence ?? 0} icon={ShieldAlert} tone="var(--cat-violence)" sub={unavailable ? "غير معروف" : deltaLabel(types.Violence ?? 0, comparisonViolence)} spark={hasData ? timeline.map((bucket) => bucket.Violence) : undefined} onDrill={(types.Violence ?? 0) > 0 ? () => openInIncidents({ type: "Violence" }) : undefined} />
        <StatCard label={<>زمن احتساب القرار (خادم) <bdi dir="ltr">p50 / p95</bdi></>} value={latency.p50 === null ? "لا توجد قياسات" : `${latency.p50} / ${latency.p95 ?? "—"} ms`} icon={Timer} tone="var(--signal)" sub={latency.p50 === null ? "p95 يتطلب قياسين — ليس زمن الوصول" : `${latencySamples.length} قياس · ليس زمن الوصول للتنبيه`} spark={latencySpark.length > 1 ? latencySpark : undefined} onDrill={latency.p50 !== null ? () => openInIncidents({}) : undefined} />
        <StatCard label="الكاميرات النشطة" value="غير متاح" icon={Camera} sub="لا ترد حالة المصدر هنا" />
      </>}
    </div>

    <details className="stats-legend"><summary>ما يقيسه كل رقم</summary><dl>{STATS_LEGEND.map((item) => <div key={item.term}><dt>{item.term}</dt><dd>{item.definition}</dd></div>)}</dl></details>

    {!hasContextData && <section className="offline-panel"><div className="offline-icon"><CircleHelp size={27} /></div><div><span className="eyebrow">حالة البيانات</span><h2>{isOffline ? "الخادم غير متصل — لا توجد تنبيهات للعرض" : "لا توجد تنبيهات ضمن التصفية"}</h2><p>{isOffline ? <>شغّل خدمة التحليل المحلية بالأمر <code dir="ltr">python backend/api.py</code> ثم أعد التحقق من القناة.</> : "غيّر الفترة أو امسح عوامل التصفية لاستعراض التنبيهات المستلمة."}</p><div className="offline-actions">{process.env.NODE_ENV !== "production" && !fixtureMode && <a href="/?fixtures=1">عرض بيانات تجريبية <ChevronLeft size={14} /></a>}{chips.length > 0 && <button onClick={() => onFiltersChange({ range: "all" })}>مسح التصفية</button>}</div></div></section>}
    {hasContextData && <>{activeSource === "persisted" && <p className="chart-scope-note">الرسوم البيانية أدناه من نطاق الجلسة (التنبيهات المستلمة)؛ اختيار «سجل الأدلة» يغيّر المؤشرات الرقمية فقط.</p>}<OverviewCharts alerts={visible} timelineAlerts={chartDimensions.timeline} cameraAlerts={chartDimensions.camera} severityAlerts={chartDimensions.severity} confidenceAlerts={chartDimensions.confidence} filters={filters} onFiltersChange={onFiltersChange} now={now} selectedWindow={customWindow} onWindowChange={setCustomWindow} hoveredCamera={hoveredCamera} onHoveredCameraChange={setHoveredCamera} hoveredBucket={hoveredBucket} onHoveredBucketChange={setHoveredBucket} /><section className="latest-panel"><div className="latest-heading"><div><span className="section-index instrument-num">03</span><h3>أحدث التنبيهات</h3></div><span>اضغط على التنبيه لمراجعته</span></div><div className="latest-list">{visible.length === 0 && <div className="latest-empty">لا تنبيهات تطابق التصفية الحالية.</div>}{visible.slice(0, 5).map((alert) => <button key={alert.id} className={`latest-row severity-${alert.severity} ${hoveredCamera && alert.cameraId !== hoveredCamera || hoveredBucket && !inTimeWindow(alert, hoveredBucket) ? "is-muted" : ""}`} onMouseEnter={() => setHoveredCamera(alert.cameraId)} onMouseLeave={() => setHoveredCamera(null)} onClick={() => onSelectIncident(alert)}><span className="latest-severity"><i />{SEVERITY_LABELS[alert.severity as SeverityKey]}</span><span className="latest-type">{ALERT_TYPE_LABELS[alert.type]}<small>{alert.location}</small></span><bdi className="latest-camera instrument-num">{alert.cameraId}</bdi><span className="latest-time">{relativeArabic(alert.isoTime, now)}</span><ChevronLeft size={15} /></button>)}</div></section></>}
    <div className="overview-footnote">كل رقم هنا يعدّ <bdi>التنبيهات</bdi> الواردة خلال هذه الجلسة (حتى {SESSION_ALERT_CAP} تنبيهًا)، وليس الكشوفات أو الأشخاص أو الحوادث المُراجَعة. اختيار «سجل الأدلة» يعرض سجلات الأدلة المخزَّنة حسب وقت تسجيلها. الأرقام ليست قياساً لاكتمال الرصد أو دقّة النموذج.</div>
  </div>
}
