"use client"

import dynamic from "next/dynamic"
import { Activity, Camera, ChevronLeft, CircleHelp, Clapperboard, Radio } from "lucide-react"
import { useState, type ReactNode } from "react"
import type { LiveAlert } from "@/components/video-player"
import { AlertHistory } from "@/components/alert-history"
import { OverlaySettingsPanel, type OverlaySettings } from "@/components/overlay-settings"
import type { CrossFilters } from "@/lib/sentinel-selectors"
import type { ConnectionStatus } from "@/lib/sentinel-store"
import { selectVisibleAlerts } from "@/lib/sentinel-selectors"
import type { SourceVisualState } from "@/lib/live-visual-state"

const VideoPlayer = dynamic(() => import("@/components/video-player").then((module) => module.VideoPlayer), { ssr: false })

export type LiveSourceId = "CAM-01" | "CAM-02"
export type DemoSourceId = "EXAMPLE-01" | "EXAMPLE-02" | "EXAMPLE-03"
const LIVE_SOURCES: LiveSourceId[] = ["CAM-01", "CAM-02"]
const DEMO_SOURCES: { id: DemoSourceId; title: string }[] = [
  { id: "EXAMPLE-01", title: "عينة اعتداء 1" },
  { id: "EXAMPLE-02", title: "عينة اعتداء 2" },
  { id: "EXAMPLE-03", title: "عينة عنف 3" },
]
const STATE_LABEL: Record<SourceVisualState, string> = {
  live: "مباشر", replay: "إعادة تشغيل", stale: "بيانات قديمة", offline: "متوقف", loading: "جارٍ الاتصال", unverified: "مصدر غير موثق",
}
const STATE_COLOR: Record<SourceVisualState, string> = {
  live: "var(--state-live)", replay: "var(--state-replay)", stale: "var(--state-stale)", offline: "var(--state-offline)", loading: "var(--state-stale)", unverified: "var(--state-stale)",
}
type Props = {
  mode: "monitor" | "demo"
  liveSource: LiveSourceId
  onLiveSourceChange: (id: LiveSourceId) => void
  demoSource: DemoSourceId | null
  onDemoSourceChange: (id: DemoSourceId) => void
  alerts: LiveAlert[]
  selectedAlert: LiveAlert | null
  onSelectAlert: (alert: LiveAlert) => void
  feed: ReactNode
  filters: CrossFilters
  onFiltersChange: (filters: CrossFilters) => void
  privacyMode: boolean
  personCount: number
  overlaySettings: OverlaySettings
  onOverlaySettingsChange: (settings: OverlaySettings) => void
  fixtureMode: boolean
  connectionStatus: ConnectionStatus
  canStartDemo: boolean
}

function StatusBadge({ state }: { state: SourceVisualState }) {
  return <span className="inline-flex items-center gap-1.5 rounded border px-2 py-1 text-[10px] font-semibold" style={{ color: STATE_COLOR[state], borderColor: `color-mix(in srgb, ${STATE_COLOR[state]} 38%, var(--border-hairline))`, backgroundColor: `color-mix(in srgb, ${STATE_COLOR[state]} 8%, var(--surface-1))` }}><span className="size-1.5 rounded-full bg-current" />{STATE_LABEL[state]}</span>
}

function SectionHeader({ mode, fixtureMode }: { mode: Props["mode"]; fixtureMode: boolean }) {
  const monitor = mode === "monitor"
  return <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
    <div>
      <div className="eyebrow"><span className="eyebrow-line" />لوحة القيادة / <bdi dir="ltr" className="instrument-num">{monitor ? "02" : "03"}</bdi></div>
      <h1 className="mt-1 text-[clamp(24px,2.2vw,32px)] font-bold leading-tight tracking-tight">{monitor ? "المراقبة الحية" : "المقاطع التجريبية"}<span className="font-normal text-[var(--text-secondary)]"> {monitor ? "/ جدار الفيديو" : "/ مكتبة المعاينة"}</span></h1>
      <p className="mt-1 text-xs leading-6 text-[var(--text-tertiary)]">{monitor ? "عرض المصادر المهيأة وقراءات التحليل الواردة لكل كاميرا." : "تُشغَّل العينات المحلية عند اختيارها. النتائج هنا إعادة تشغيل وليست رصداً مباشراً."}</p>
    </div>
    <div className="flex items-center gap-2 rounded-md border border-[var(--border-hairline)] bg-[var(--surface-1)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
      {monitor ? <Radio size={14} className="text-[var(--signal)]" /> : <Clapperboard size={14} className="text-[var(--state-replay)]" />}
      {fixtureMode ? "معاينة تجريبية للواجهة" : monitor ? "حالة الفيديو تُؤخذ من المصدر المختار" : "عينات محلية عند الطلب"}
    </div>
  </header>
}

export function UiMonitorSection(props: Props) {
  const { mode, liveSource, onLiveSourceChange, demoSource, onDemoSourceChange, alerts, selectedAlert, onSelectAlert, feed, filters, onFiltersChange, privacyMode, personCount, overlaySettings, onOverlaySettingsChange, fixtureMode, connectionStatus, canStartDemo } = props
  const monitor = mode === "monitor"
  const source = monitor ? (LIVE_SOURCES.includes(filters.cameraId as LiveSourceId) ? filters.cameraId as LiveSourceId : liveSource) : demoSource
  const [sourceState, setSourceState] = useState<SourceVisualState>("offline")
  const displayState = fixtureMode || connectionStatus !== "online" ? "offline" : sourceState
  const relevantAlert = source ? alerts.find((alert) => alert.cameraId === source) ?? null : null
  return <div className="mx-auto flex min-h-full max-w-[1600px] flex-col px-4 pb-6 pt-5 md:px-7">
    <SectionHeader mode={mode} fixtureMode={fixtureMode} />
    <div className="mb-3 flex items-center justify-between gap-3"><div className="flex items-center gap-2"><span className="section-index instrument-num">01</span><h2 className="text-[13px] font-semibold">{monitor ? "مصادر الكاميرا" : "مكتبة المقاطع"}</h2><span className="h-px w-10 bg-[var(--border-hairline)]" /></div><span className="text-[10px] text-[var(--text-tertiary)]">{monitor ? "اختر مصدراً للعرض" : "اختر عينة لبدء التحليل"}</span></div>
    <div className={`mb-4 grid gap-2 ${monitor ? "grid-cols-2" : "custom-scrollbar grid-flow-col auto-cols-[minmax(230px,75%)] overflow-x-auto pb-1 sm:grid-flow-row sm:grid-cols-3 sm:overflow-visible sm:pb-0"}`}>
      {monitor ? LIVE_SOURCES.map((id, index) => <button key={id} type="button" aria-pressed={source === id} onClick={() => { onLiveSourceChange(id); onFiltersChange({ ...filters, cameraId: id }); setSourceState("loading") }} className={`group flex min-w-0 items-center gap-2 rounded-lg border px-2 py-3 text-start focus-visible:outline-2 focus-visible:outline-[var(--signal)] sm:gap-3 sm:px-3 ${source === id ? "border-[var(--signal)] bg-[var(--surface-2)]" : "border-[var(--border-hairline)] bg-[var(--surface-1)] hover:border-[var(--text-tertiary)]"}`}><div className="hidden size-10 flex-none place-items-center rounded-md border border-[var(--border-hairline)] bg-[var(--surface-0)] text-[var(--text-tertiary)] sm:grid"><Camera size={18} /></div><div className="min-w-0 flex-1"><span className="block whitespace-nowrap text-xs font-semibold">كاميرا {index + 1}</span><bdi className="instrument-num block whitespace-nowrap text-[10px] text-[var(--text-tertiary)]" dir="ltr">{id}</bdi></div>{source === id ? <StatusBadge state={displayState} /> : <span className="text-[10px] text-[var(--text-tertiary)]">لم يُفحص</span>}</button>) : DEMO_SOURCES.map((item, index) => <button key={item.id} type="button" disabled={!canStartDemo} aria-pressed={demoSource === item.id} onClick={() => { onDemoSourceChange(item.id); setSourceState("loading") }} className={`group flex min-w-0 overflow-hidden rounded-lg border text-start focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:cursor-not-allowed disabled:opacity-40 ${demoSource === item.id ? "border-[var(--state-replay)] bg-[var(--surface-2)]" : "border-[var(--border-hairline)] bg-[var(--surface-1)] hover:border-[var(--text-tertiary)]"}`}><span className="relative grid w-20 flex-none place-items-center border-e border-[var(--border-hairline)] bg-[var(--surface-0)] text-[var(--state-replay)] sm:w-24"><span className="absolute inset-0 opacity-20 [background-image:linear-gradient(var(--border-hairline)_1px,transparent_1px),linear-gradient(90deg,var(--border-hairline)_1px,transparent_1px)] [background-size:13px_13px]" /><Clapperboard size={22} className="relative" /><span className="instrument-num absolute bottom-1 start-1 text-[9px]">0{index + 1}</span></span><span className="flex min-w-0 flex-1 flex-col justify-center gap-1 px-3 py-3"><span className="truncate text-xs font-semibold">{item.title}</span><bdi className="instrument-num text-[10px] text-[var(--text-tertiary)]" dir="ltr">{item.id}</bdi><span className="text-[10px] text-[var(--state-replay)]">تجريبي</span></span><ChevronLeft size={14} className="m-3 self-center text-[var(--text-tertiary)]" /></button>)}
    </div>
    {!monitor && !canStartDemo && <p className="-mt-2 mb-4 text-[10px] text-[var(--text-tertiary)]">صلاحية المسؤول مطلوبة لتشغيل التحليل على العينات.</p>}
    <div className="grid min-h-[580px] flex-1 gap-3 xl:h-[calc(100dvh-340px)] xl:min-h-[520px] xl:max-h-[660px] xl:flex-none xl:grid-cols-[minmax(0,1fr)_300px]">
      <section className="flex min-h-[540px] min-w-0 flex-col overflow-hidden rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] shadow-[var(--shadow-panel)]" aria-label={monitor ? "عرض الكاميرا المختارة" : "عرض المقطع المختار"}>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-hairline)] px-4 py-2.5"><div className="flex items-center gap-2"><Activity size={15} className="text-[var(--signal)]" /><strong className="text-xs">{monitor ? "المشهد الرئيسي" : "تشغيل العينة"}</strong>{source && <bdi className="instrument-num rounded border border-[var(--border-hairline)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]" dir="ltr">{source}</bdi>}</div><div className="flex items-center gap-2">{source && <StatusBadge state={displayState} />}<OverlaySettingsPanel settings={overlaySettings} onChange={onOverlaySettingsChange} /></div></div>
        <div className="min-h-[460px] flex-1">{source && !fixtureMode && connectionStatus === "online" ? <VideoPlayer key={source} cameraId={source} activeAlert={relevantAlert} privacyMode={privacyMode} personCount={personCount} overlaySettings={overlaySettings} onSourceStateChange={setSourceState} /> : <div className="relative flex h-full min-h-[460px] flex-col items-center justify-center overflow-hidden bg-[var(--surface-0)] px-5 text-center"><div className="absolute inset-0 opacity-20 [background-image:linear-gradient(var(--border-hairline)_1px,transparent_1px),linear-gradient(90deg,var(--border-hairline)_1px,transparent_1px)] [background-size:32px_32px]" /><div className="relative grid size-20 place-items-center rounded-full border border-[var(--border-hairline)] text-[var(--state-offline)]">{monitor ? <Camera size={32} /> : <Clapperboard size={32} />}</div><span className="relative mt-5 text-sm font-semibold">{monitor ? "البث المباشر غير متاح" : source ? "خدمة إعادة التشغيل غير متاحة" : "لم يُحدَّد مقطع بعد"}</span><p className="relative mt-2 max-w-sm text-xs leading-6 text-[var(--text-tertiary)]">{monitor ? "لا توجد صورة مؤكدة من المصدر المختار. تُعرض التنبيهات المستلمة منفصلة عن حالة الفيديو." : source ? "تعذّر الاتصال بخدمة المقاطع المحلية. أعد المحاولة عند اتصال الخادم." : "اختر عينة من مكتبة المقاطع أعلاه لبدء إعادة التشغيل والتحليل المحلي."}</p><span className="relative mt-5 rounded border border-[var(--state-offline)] px-2 py-1 text-[10px] text-[var(--state-offline)]">{fixtureMode ? "عينة واجهة · لا يوجد فيديو مباشر" : "حالة المصدر غير مؤكدة"}</span></div>}</div>
      </section>
      <aside className="flex min-h-[380px] min-w-0 flex-col overflow-hidden rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] xl:h-full" aria-label="التنبيهات المستلمة">
        <div className="min-h-0 flex-1 overflow-hidden">{feed}</div>
        <AlertHistory compact alerts={selectVisibleAlerts(alerts, filters)} selectedAlertId={selectedAlert?.id ?? null} onSelectAlert={onSelectAlert} />
      </aside>
    </div>
    <div className="mt-3 flex items-start gap-2 text-[10px] leading-5 text-[var(--text-tertiary)]"><CircleHelp size={13} className="mt-0.5 flex-none" />{monitor ? "وسم مباشر يتطلب إطاراً وارداً ومصدر بث حي وبيانات تحليل حديثة. حالة قناة التنبيهات وحدها لا تثبت حالة الفيديو." : "التنبيهات وقياسات الأداء المعروضة تخص المصدر المتصل فقط؛ المقاطع التجريبية لا تمثل كاميرا حية."}</div>
  </div>
}
