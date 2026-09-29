"use client"

import dynamic from "next/dynamic"
import { useEffect, useMemo, useState, type ReactNode } from "react"
import { Activity, ArrowUpLeft, Camera, CircleHelp, FileText, Radio, RefreshCw, Server, ShieldAlert } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"
import { apiFetch } from "@/lib/api-auth"
import { countsBySeverity, countsByType, selectVisibleAlerts, type CrossFilters } from "@/lib/sentinel-selectors"
import { useSentinel } from "@/lib/sentinel-store"
import { InstrumentValue } from "@/components/shell/primitives"
import { formatTime24 } from "@/components/shell/locale"

const AiReport = dynamic(() => import("@/components/ai-report").then(module => module.AiReport), { ssr: false })
const GeoDashboard = dynamic(() => import("@/components/geo-dashboard").then(module => module.GeoDashboard), { ssr: false })
const TelegramStatusCard = dynamic(() => import("@/components/telegram-status").then(module => module.TelegramStatusCard), { ssr: false })
const ApiAccess = dynamic(() => import("@/components/api-access").then(module => module.ApiAccess), { ssr: false })
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

const PANEL = "rounded-[var(--radius-panel)] border border-[var(--border-hairline)] bg-[var(--surface-1)]"
const ACTION = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-[var(--border-hairline)] px-3 text-xs text-[var(--text-secondary)] hover:border-[var(--signal)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)]"
const SEVERITY_LABEL = { critical: "حرج", high: "مرتفع", medium: "متوسط" } as const
const SEVERITY_COLOR = { critical: "var(--threat-critical)", high: "var(--threat-high)", medium: "var(--threat-medium)" } as const

function Heading({ index, title, muted, description, aside }: { index: string; title: string; muted: string; description: string; aside?: ReactNode }) {
  return <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
    <div><div className="flex items-center gap-2 text-[10px] font-semibold text-[var(--signal)]"><span className="h-px w-4 bg-[var(--signal)]" />لوحة القيادة / <bdi dir="ltr" className="instrument-num">{index}</bdi></div>
      <h1 className="mt-1 text-[clamp(24px,2.2vw,32px)] font-bold leading-[1.3] tracking-tight">{title} <span className="font-normal text-[var(--text-secondary)]">{muted}</span></h1>
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">{description}</p></div>{aside}
  </div>
}

function FilterStrip({ filters, setFilters }: { filters: CrossFilters; setFilters: (filters: CrossFilters) => void }) {
  const active: { key: "cameraId" | "severity" | "type" | "confidenceBand"; label: string }[] = []
  if (filters.cameraId) active.push({ key: "cameraId", label: filters.cameraId })
  if (filters.severity) active.push({ key: "severity", label: SEVERITY_LABEL[filters.severity] })
  if (filters.type) active.push({ key: "type", label: filters.type === "Weapon" ? "سلاح" : "اعتداء" })
  if (filters.confidenceBand !== undefined) active.push({ key: "confidenceBand", label: `ثقة ${filters.confidenceBand * 20}–${filters.confidenceBand * 20 + 20}%` })
  if (!active.length) return null
  return <div className="mb-3 flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]"><span>التصفية النشطة</span>{active.map(item => <button key={item.key} className={ACTION} onClick={() => setFilters({ ...filters, [item.key]: undefined })} aria-label={`إزالة تصفية ${item.label}`}><bdi dir={item.key === "cameraId" ? "ltr" : undefined}>{item.label}</bdi> ×</button>)}<button className={ACTION} onClick={() => setFilters({ range: filters.range })}>مسح الكل</button></div>
}

function Empty({ title, detail }: { title: string; detail: string }) {
  return <div className={`${PANEL} flex min-h-40 items-start gap-4 p-6`}><CircleHelp size={24} className="shrink-0 text-[var(--state-offline)]" /><div><h2 className="font-semibold">{title}</h2><p className="mt-1 text-xs leading-6 text-[var(--text-secondary)]">{detail}</p></div></div>
}

function IncidentList({ alerts, activeId, onSelect }: { alerts: LiveAlert[]; activeId?: string; onSelect: (alert: LiveAlert) => void }) {
  return <section className={PANEL} aria-label="الحوادث ضمن التصفية"><div className="flex items-center justify-between border-b border-[var(--border-hairline)] px-4 py-3"><h2 className="text-sm font-semibold">حوادث الفترة</h2><bdi dir="ltr" className="instrument-num text-xs text-[var(--text-tertiary)]">{alerts.length}</bdi></div>
    {alerts.length ? <div className="max-h-[610px] overflow-y-auto">{alerts.map(alert => <button key={alert.id} onClick={() => onSelect(alert)} aria-current={activeId === alert.id ? "true" : undefined} className={`flex w-full items-center gap-3 border-b border-[var(--border-hairline)] px-4 py-3 text-start last:border-0 hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] ${activeId === alert.id ? "bg-[var(--surface-2)]" : ""}`}><span className="h-2 w-2 shrink-0 rounded-full" style={{ background: SEVERITY_COLOR[alert.severity] }} /><span className="min-w-0 flex-1"><strong className="block truncate text-xs">{alert.type === "Weapon" ? "رصد سلاح" : "رصد اعتداء"}</strong><small className="mt-1 block truncate text-[10px] text-[var(--text-tertiary)]">{alert.location}</small></span><bdi dir="ltr" className="instrument-num text-[10px] text-[var(--text-secondary)]">{alert.cameraId}</bdi></button>)}</div> : <p className="p-4 text-xs leading-6 text-[var(--text-tertiary)]">لا توجد حوادث ضمن عوامل التصفية الحالية.</p>}
  </section>
}

function FixtureSummary({ alert }: { alert: LiveAlert }) {
  const type = alert.type === "Weapon" ? "رصد سلاح" : "رصد اعتداء"
  return <article className={`${PANEL} overflow-hidden`}>
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border-hairline)] p-5"><div><span className="text-[10px] font-semibold text-[var(--state-replay)]">عينة واجهة · صياغة من حقول التنبيه</span><h3 className="mt-2 text-lg font-semibold">ملخص سجل الحادثة</h3><p className="mt-1 text-xs text-[var(--text-secondary)]">قراءة منظّمة للحقول التجريبية المعروضة، دون اتصال بسجل أدلة.</p></div><span className="rounded border border-[var(--border-hairline)] px-2 py-1 text-[10px] text-[var(--text-tertiary)]">معاينة / حقائق</span></header>
    <div className="space-y-5 p-5 text-[13px] leading-8"><section><h4 className="mb-2 text-[11px] font-semibold text-[var(--signal)]">الوقائع المسجلة في العينة</h4><p>تعرض العينة تنبيهاً من نوع {type} في {alert.location} عبر المصدر <bdi dir="ltr" className="instrument-num">{alert.cameraId}</bdi>. صُنّف مستوى الخطورة في سجل التنبيه بأنه {SEVERITY_LABEL[alert.severity]}.</p></section><section className="border-t border-[var(--border-hairline)] pt-4"><h4 className="mb-2 text-[11px] font-semibold text-[var(--signal)]">مصدر المعلومات</h4><p>القيم أعلاه مأخوذة من تنبيه المعاينة <bdi dir="ltr" className="instrument-num">{alert.id}</bdi>. لا توجد لهذا التنبيه أدلة فيديو أو خلاصة محلية محفوظة على الخادم.</p></section><section className="rounded border-s-2 border-[var(--cat-violence)] bg-[var(--surface-2)] px-4 py-3"><h4 className="text-[11px] font-semibold text-[var(--cat-violence)]">تفسير النموذج</h4><p className="text-xs text-[var(--text-secondary)]">غير متاح لهذه العينة. لا تُستنتج دوافع أو نتائج من حقول التنبيه وحدها.</p></section></div>
  </article>
}

function Intelligence({ visible, active, fixtureMode, onSelect, filters, setFilters }: { visible: LiveAlert[]; active: LiveAlert | null; fixtureMode: boolean; onSelect: (alert: LiveAlert) => void; filters: CrossFilters; setFilters: (filters: CrossFilters) => void }) {
  return <><Heading index="05" title="التحليل" muted="الذكي" description="سجل حقائق الحادثة ومصدر كل عبارة؛ تبقى استنتاجات النموذج مميزة عن الوقائع." aside={<span className="text-[11px] text-[var(--text-tertiary)]">المصدر: التنبيهات المستلمة في هذه الجلسة</span>} />
    <div className="grid items-start gap-3 lg:grid-cols-[minmax(230px,280px)_minmax(0,1fr)]"><IncidentList alerts={visible} activeId={active?.id} onSelect={onSelect} /><div className="min-w-0 space-y-3">{active ? <><section className={`${PANEL} p-5`}><div className="flex flex-wrap items-start justify-between gap-3"><div><span className="text-[10px] font-semibold text-[var(--signal)]">سجل الحادثة / بيانات التنبيه</span><h2 className="mt-1 text-lg font-semibold"><button className="hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]" onClick={() => setFilters({ ...filters, type: filters.type === active.type ? undefined : active.type })} aria-pressed={filters.type === active.type}>{active.type === "Weapon" ? "رصد سلاح" : "رصد اعتداء"}</button></h2></div><button className="rounded border px-2 py-1 text-xs font-semibold focus-visible:outline-2 focus-visible:outline-[var(--signal)]" style={{ color: SEVERITY_COLOR[active.severity], borderColor: SEVERITY_COLOR[active.severity] }} onClick={() => setFilters({ ...filters, severity: filters.severity === active.severity ? undefined : active.severity })} aria-pressed={filters.severity === active.severity}>{SEVERITY_LABEL[active.severity]}</button></div><dl className="mt-5 grid gap-4 border-t border-[var(--border-hairline)] pt-4 text-xs sm:grid-cols-3"><div><dt className="text-[var(--text-tertiary)]">المصدر</dt><dd className="mt-1"><button className="instrument-num hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]" onClick={() => setFilters({ ...filters, cameraId: filters.cameraId === active.cameraId ? undefined : active.cameraId })} aria-pressed={filters.cameraId === active.cameraId}><bdi dir="ltr">{active.cameraId}</bdi></button></dd></div><div><dt className="text-[var(--text-tertiary)]">الموقع المسجل</dt><dd className="mt-1">{active.location}</dd></div><div><dt className="text-[var(--text-tertiary)]">معرّف التنبيه</dt><dd className="mt-1 break-all"><bdi dir="ltr" className="instrument-num">{active.id}</bdi></dd></div></dl></section>{fixtureMode ? <FixtureSummary alert={active} /> : <AiReport alertId={active.id} />}</> : <Empty title="لا توجد حادثة للعرض" detail="اختر حادثة من القائمة، أو عدّل عوامل التصفية. لا يمكن إنشاء تقرير دون سجل حادثة محفوظ." />}</div></div></>
}

function Operations({ visible, active, filters, setFilters, connectionStatus, fixtureMode }: { visible: LiveAlert[]; active: LiveAlert | null; filters: CrossFilters; setFilters: (filters: CrossFilters) => void; connectionStatus: string; fixtureMode: boolean }) {
  const severity = countsBySeverity(visible)
  const unavailable = connectionStatus !== "online" && !fixtureMode && visible.length === 0
  return <><Heading index="06" title="غرفة" muted="العمليات" description="توزيع الحوادث المستلمة على مخطط مناطق توضيحي وقناة الإشعارات." /><div className="mb-3 flex flex-wrap gap-2"><span className={`${PANEL} px-3 py-2 text-xs text-[var(--text-secondary)]`}>التنبيهات المستلمة ضمن التصفية <bdi dir="ltr" className="instrument-num ms-2 text-[var(--text-primary)]">{unavailable ? "—" : visible.length}</bdi></span>{(["critical", "high", "medium"] as const).map(level => <button key={level} className={ACTION} onClick={() => setFilters({ ...filters, severity: filters.severity === level ? undefined : level })} aria-pressed={filters.severity === level}><span className="h-2 w-2 rounded-full" style={{ background: SEVERITY_COLOR[level] }} />{SEVERITY_LABEL[level]} <bdi dir="ltr" className="instrument-num">{unavailable ? "—" : severity[level] ?? 0}</bdi></button>)}</div><div className="grid items-start gap-3 xl:grid-cols-[minmax(0,1fr)_310px]"><GeoDashboard alert={active} alerts={visible} focusCameraId={filters.cameraId ?? ""} onCameraSelect={cameraId => setFilters({ ...filters, cameraId: filters.cameraId === cameraId ? undefined : cameraId })} fixtureMode={fixtureMode} connectionStatus={connectionStatus} /><div className="space-y-3"><TelegramStatusCard /><div className={`${PANEL} p-4 text-xs leading-6 text-[var(--text-tertiary)]`}>المخطط تمثيلي مستمد من مواقع العرض السابقة؛ مواضع الكاميرات ليست إحداثيات موثّقة. حجم العلامة وعددها مشتقان من التنبيهات المستلمة ضمن التصفية.</div></div></div></>
}

type Health = { health?: string; model?: { device?: string } }
function System({ visible, alerts, connectionStatus, fixtureMode, filters, setFilters }: { visible: LiveAlert[]; alerts: LiveAlert[]; connectionStatus: string; fixtureMode: boolean; filters: CrossFilters; setFilters: (filters: CrossFilters) => void }) {
  const [health, setHealth] = useState<Health | null>(null)
  const [healthState, setHealthState] = useState<"loading" | "ready" | "offline">(fixtureMode || connectionStatus !== "online" ? "offline" : "loading")
  const [checkedAt, setCheckedAt] = useState<string | null>(null)
  useEffect(() => { if (fixtureMode || connectionStatus !== "online") return; const controller = new AbortController(); const check = async () => { try { const response = await apiFetch(`${API_BASE}/health`, { signal: controller.signal }); if (!response.ok) throw new Error("health unavailable"); const data: Health = await response.json(); if (!controller.signal.aborted) { setHealth(data); setHealthState("ready"); setCheckedAt(formatTime24(new Date())) } } catch { if (!controller.signal.aborted) { setHealth(null); setHealthState("offline"); setCheckedAt(null) } } }; void check(); const timer = window.setInterval(check, 30_000); return () => { controller.abort(); window.clearInterval(timer) } }, [connectionStatus, fixtureMode])
  const serverState = fixtureMode || connectionStatus !== "online" ? "offline" : healthState
  const severity = countsBySeverity(visible)
  const types = countsByType(visible)
  const streamLabel = connectionStatus === "online" ? "متصلة" : connectionStatus === "reconnecting" ? "إعادة اتصال" : "غير متصلة"
  return <><Heading index="07" title="حالة" muted="النظام" description="حالة القنوات والخادم وبيانات الجلسة، مع توضيح مصدر كل قراءة." aside={<button className={ACTION} onClick={() => window.location.reload()}><RefreshCw size={14} />إعادة التحقق</button>} /><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    <StatusCard icon={<Radio size={18} />} label="قناة التنبيهات" value={streamLabel} source="اتصال SSE في المتصفح" detail="الاتصال لا يثبت سلامة الكاميرات أو النماذج." tone={connectionStatus === "online" ? "var(--state-live)" : "var(--state-offline)"} />
    <StatusCard icon={<Server size={18} />} label="استجابة الخادم" value={serverState === "loading" ? "جارٍ التحقق" : serverState === "ready" ? health?.health === "ok" ? "الخادم يستجيب" : "حالة غير معروفة" : "غير متاح"} source="GET /health" detail={checkedAt ? `آخر تحقق: ${checkedAt}` : "لا توجد استجابة موثقة بعد"} tone={serverState === "ready" ? "var(--signal)" : "var(--state-offline)"} />
    <StatusCard icon={<Activity size={18} />} label="جهاز الاستدلال" value={serverState === "ready" && health?.model?.device ? health.model.device.toUpperCase() : "غير متاح"} source="/health · model.device" detail="ما يبلّغ به الخادم؛ ليس قياساً لأداء الاستدلال." tone="var(--text-secondary)" />
    <StatusCard icon={<Camera size={18} />} label="صحة الكاميرات" value="غير متاح" source="لا توجد قراءة صحة للمصدر هنا" detail="قناة التنبيهات وحدها لا تكفي للتحقق." tone="var(--state-offline)" />
  </div><div className="mt-3 grid items-start gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.85fr)]"><section className={PANEL}><div className="flex items-center gap-2 border-b border-[var(--border-hairline)] p-4"><ShieldAlert size={17} className="text-[var(--signal)]" /><h2 className="text-sm font-semibold">تنبيهات الجلسة</h2></div><div className="grid grid-cols-2 gap-px bg-[var(--border-hairline)] sm:grid-cols-3">{[["المستلمة", alerts.length, "مخزن الجلسة"], ["ضمن التصفية", visible.length, "مرشح الواجهة"], ["حرجة", severity.critical ?? 0, "خطورة التنبيه"], ["مرتفعة", severity.high ?? 0, "خطورة التنبيه"], ["أسلحة", types.Weapon ?? 0, "نوع التنبيه"], ["اعتداءات", types.Violence ?? 0, "نوع التنبيه"]].map(([label, value, source]) => <div key={label} className="bg-[var(--surface-1)] p-4"><span className="text-[11px] text-[var(--text-secondary)]">{label}</span><strong className="instrument-num mt-2 block text-xl">{fixtureMode || alerts.length || connectionStatus === "online" ? value : "—"}</strong><small className="text-[10px] text-[var(--text-tertiary)]">{fixtureMode ? "عينة واجهة · " : ""}{source}</small></div>)}</div><div className="flex flex-wrap gap-2 p-4"><button className={ACTION} aria-pressed={filters.type === "Weapon"} onClick={() => setFilters({ ...filters, type: filters.type === "Weapon" ? undefined : "Weapon" })}>تصفية الأسلحة</button><button className={ACTION} aria-pressed={filters.type === "Violence"} onClick={() => setFilters({ ...filters, type: filters.type === "Violence" ? undefined : "Violence" })}>تصفية الاعتداءات</button></div></section><div className="space-y-3"><section className={PANEL}><div className="flex items-center gap-2 border-b border-[var(--border-hairline)] p-4"><FileText size={17} className="text-[var(--signal)]" /><h2 className="text-sm font-semibold">وصول واجهة البرمجة</h2></div><ApiAccess /></section><TelegramStatusCard /></div></div><p className="mt-3 text-[10px] text-[var(--text-tertiary)]">هذه مؤشرات استقبال الواجهة خلال الجلسة، وليست نتائج اختبار أداء أو دقة للنظام. <ArrowUpLeft size={11} className="inline" /></p></>
}

function StatusCard({ icon, label, value, source, detail, tone }: { icon: ReactNode; label: string; value: string; source: string; detail: string; tone: string }) {
  return <div className={`${PANEL} min-h-40 p-4`}><div className="flex items-center justify-between text-[11px] text-[var(--text-secondary)]"><span>{label}</span><span style={{ color: tone }}>{icon}</span></div><strong className="mt-4 block text-xl" style={{ color: tone }}><InstrumentValue value={value} /></strong><p className="mt-2 text-[10px] text-[var(--text-tertiary)]">المصدر: <bdi dir={source.includes("/") ? "ltr" : undefined}>{source}</bdi></p><p className="mt-1 text-[10px] leading-5 text-[var(--text-tertiary)]">{detail}</p></div>
}

export function UiIntelOpsSection({ section }: { section: "intelligence" | "operations" | "system" }) {
  const { alerts, selectedAlert, selectAlert, filters, setFilters, connectionStatus, fixtureMode } = useSentinel()
  const visible = useMemo(() => selectVisibleAlerts(alerts, filters), [alerts, filters])
  const active = selectedAlert && visible.some(alert => alert.id === selectedAlert.id) ? selectedAlert : visible[0] ?? null
  return <div className="mx-auto max-w-[1510px] px-3 py-4 sm:px-7 sm:py-6" dir="rtl"><FilterStrip filters={filters} setFilters={setFilters} />{section === "intelligence" ? <Intelligence visible={visible} active={active} fixtureMode={fixtureMode} onSelect={selectAlert} filters={filters} setFilters={setFilters} /> : section === "operations" ? <Operations visible={visible} active={active} filters={filters} setFilters={setFilters} connectionStatus={connectionStatus} fixtureMode={fixtureMode} /> : <System visible={visible} alerts={alerts} connectionStatus={connectionStatus} fixtureMode={fixtureMode} filters={filters} setFilters={setFilters} />}</div>
}
