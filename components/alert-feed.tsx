"use client"

import { memo, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { Bell, Camera, ChevronLeft, ChevronRight, Crosshair, ShieldAlert, WifiOff } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"
import { CategoryFilter } from "./category-filter"
import { formatAlertRelativeArabic, type DetectionCategory } from "@/lib/detection-types"
import { useSentinel } from "@/lib/sentinel-store"
import { REPLAY_SOURCE_PREFIX, SEVERITY_LABEL, SEVERITY_TOKEN, TRIAGE_ACTION_LABEL, TRIAGE_ALLOWED, TRIAGE_LABEL, selectVisibleAlerts, type TriageAction, type TriageState } from "@/lib/sentinel-selectors"

interface AlertFeedProps {
  alerts: LiveAlert[]
  selectedAlertId: string | null
  onSelectAlert: (alert: LiveAlert) => void
  selectedCategories: DetectionCategory[]
  onCategoryChange: (categories: DetectionCategory[]) => void
}

const WINDOW_SIZE = 80

function useFeedClock() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(timer)
  }, [])
  return now
}

export const AlertFeed = memo(function AlertFeed({ alerts, selectedAlertId, onSelectAlert, selectedCategories, onCategoryChange }: AlertFeedProps) {
  const { alerts: allAlerts, filters, setFilters, connectionStatus, fixtureMode, triage, recordTriage, rejectedEnvelopes } = useSentinel()
  const now = useFeedClock()
  const [triageBusyId, setTriageBusyId] = useState<string | null>(null)
  const categoryCounts = useMemo(() => {
    const counts = { weapon: 0, violence: 0 }
    for (const alert of selectVisibleAlerts(allAlerts, { ...filters, type: undefined }, now)) {
      if (alert.type === "Weapon") counts.weapon++
      else counts.violence++
    }
    return counts
  }, [allAlerts, filters, now])
  const [page, setPage] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)
  const lastPage = Math.max(0, Math.ceil(alerts.length / WINDOW_SIZE) - 1)
  const safePage = Math.min(page, lastPage)
  const windowed = alerts.slice(safePage * WINDOW_SIZE, (safePage + 1) * WINDOW_SIZE)

  function focusIndex(index: number) {
    if (index < 0 || index >= alerts.length) return
    setPage(Math.floor(index / WINDOW_SIZE))
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const row = listRef.current?.querySelector<HTMLButtonElement>(`[data-alert-index="${index}"]`)
      row?.focus()
      row?.scrollIntoView({ block: "nearest" })
    }))
  }

  async function applyTriageVerb(alert: LiveAlert, action: TriageAction) {
    if (fixtureMode || triageBusyId) return
    setTriageBusyId(alert.id)
    await recordTriage(alert.id, action, "")
    setTriageBusyId(null)
  }

  function handleRowKey(event: KeyboardEvent<HTMLButtonElement>, index: number, alert: LiveAlert) {
    const target = event.key === "ArrowDown" ? index + 1 : event.key === "ArrowUp" ? index - 1 : event.key === "Home" ? 0 : event.key === "End" ? alerts.length - 1 : null
    if (target !== null) { event.preventDefault(); focusIndex(target); return }
    const verb: TriageAction | null = event.key === "a" ? "acknowledge" : event.key === "c" ? "resolve" : null
    if (verb === null || !TRIAGE_ALLOWED[(triage[alert.id]?.state ?? "new") as TriageState].includes(verb)) return
    event.preventDefault()
    void applyTriageVerb(alert, verb)
  }

  const emptyIsFiltered = allAlerts.length > 0 && alerts.length === 0
  return <section aria-label="سجل التنبيهات" className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--surface-1)]">
    <div className="flex shrink-0 items-start gap-3 border-b border-[var(--border-hairline)] px-4 py-3.5">
      <div className="grid size-9 shrink-0 place-items-center rounded-md border border-[var(--border-hairline)] bg-[var(--surface-2)] text-[var(--signal)]"><Bell size={17} /></div>
      <div className="min-w-0 flex-1"><div className="text-[10px] font-semibold text-[var(--signal)]">سجل الاستلام</div><h2 className="text-[15px] font-bold leading-6">التنبيهات الواردة</h2><p className="text-[10px] text-[var(--text-tertiary)]">ضمن الفترة وعوامل التصفية المحددة</p></div>
      <bdi className="instrument-num rounded border border-[var(--border-hairline)] bg-[var(--surface-2)] px-2 py-1 text-[13px] text-[var(--text-primary)]" aria-label={`${alerts.length} تنبيه`}>{alerts.length}</bdi>
    </div>
    <CategoryFilter selectedCategories={selectedCategories} onCategoryChange={onCategoryChange} categoryCounts={categoryCounts} />
    <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-2 py-2" role="list" aria-label="التنبيهات">
      {windowed.length === 0 ? <div className="flex min-h-56 flex-col items-center justify-center px-5 text-center">
        <div className="mb-3 grid size-12 place-items-center rounded-full border border-[var(--border-hairline)] bg-[var(--surface-2)] text-[var(--text-tertiary)]">{connectionStatus === "offline" && !fixtureMode ? <WifiOff size={21} /> : <ShieldAlert size={21} />}</div>
        <strong className="text-[13px] text-[var(--text-primary)]">{emptyIsFiltered ? "لا تنبيهات تطابق التصفية" : connectionStatus === "offline" && !fixtureMode ? "قناة التنبيهات غير متصلة" : "لم ترد تنبيهات ضمن الفترة"}</strong>
        <p className="mt-1.5 max-w-64 text-[11px] leading-5 text-[var(--text-tertiary)]">{emptyIsFiltered ? "غيّر نوع التنبيه أو درجة الخطورة أو امسح التصفية." : connectionStatus === "offline" && !fixtureMode ? "تعذّر تأكيد حالة الرصد المباشر. تظهر التنبيهات هنا عند استلامها." : "يعرض السجل التنبيهات المؤكدة التي استلمتها هذه الجلسة."}</p>
        {emptyIsFiltered && <button type="button" onClick={() => setFilters({ range: filters.range })} className="mt-4 min-h-9 rounded border border-[var(--signal)] px-3 text-[11px] text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)]">مسح التصفية</button>}
      </div> : windowed.map((alert, localIndex) => {
        const index = safePage * WINDOW_SIZE + localIndex
        const severityLabel = SEVERITY_LABEL[alert.severity]
        const severityColor = SEVERITY_TOKEN[alert.severity]
        const triageState = (triage[alert.id]?.state ?? "new") as TriageState
        const weapon = alert.type === "Weapon"
        const TypeIcon = weapon ? Crosshair : ShieldAlert
        const typeColor = weapon ? "var(--cat-weapon)" : "var(--cat-violence)"
        const selected = alert.id === selectedAlertId
        const replay = alert.cameraId.startsWith(REPLAY_SOURCE_PREFIX)
        const fresh = index === 0 && now - Date.parse(alert.isoTime) < 10_000
        return <div key={alert.id} role="listitem" className={`mb-1.5 rounded-md border border-s-[3px] ${selected ? "bg-[var(--surface-3)]" : "bg-[var(--surface-2)] hover:bg-[var(--surface-3)]"} ${fresh ? "motion-safe:animate-slide-from-right" : ""}`} style={{ borderColor: "var(--border-hairline)", borderInlineStartColor: severityColor }}>
          <button type="button" data-alert-index={index} aria-current={selected ? "true" : undefined} aria-keyshortcuts="a c" onClick={() => onSelectAlert(alert)} onKeyDown={(event) => handleRowKey(event, index, alert)} className="block w-full px-3 pt-2.5 text-start focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--signal)]" aria-label={`${severityLabel}، ${weapon ? "رصد سلاح" : "رصد اعتداء"}، ${alert.cameraId}، ${formatAlertRelativeArabic(alert.isoTime, now)}، حالة المعالجة ${TRIAGE_LABEL[triageState]}`}>
            <span className="flex items-center justify-between gap-2"><span className="flex min-w-0 items-center gap-2"><TypeIcon size={15} style={{ color: typeColor }} /><strong className="truncate text-[12px] text-[var(--text-primary)]">{weapon ? "رصد سلاح" : "رصد اعتداء"}</strong></span><span className="shrink-0 text-[10px] font-semibold" style={{ color: severityColor }}>{severityLabel}</span></span>
            <span className="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-[var(--text-tertiary)]"><span className="truncate">{alert.location}</span><time dateTime={alert.isoTime}>{formatAlertRelativeArabic(alert.isoTime, now)}</time></span>
          </button>
          <div className="mt-2 flex items-center justify-between gap-2 border-t border-[var(--border-hairline)] px-3 py-1.5">
            <button type="button" aria-label={`تصفية حسب الكاميرا ${alert.cameraId}`} aria-pressed={filters.cameraId === alert.cameraId} onClick={() => setFilters({ ...filters, cameraId: filters.cameraId === alert.cameraId ? undefined : alert.cameraId })} className="flex min-h-7 items-center gap-1.5 rounded border border-[var(--border-hairline)] px-1.5 text-[10px] text-[var(--text-secondary)] hover:border-[var(--signal)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)]"><Camera size={11} /><bdi className="instrument-num" dir="ltr">{alert.cameraId}</bdi></button>
            <span className="text-[9px]" style={{ color: replay ? "var(--state-replay)" : fixtureMode ? "var(--state-stale)" : "var(--text-tertiary)" }}>{replay ? "إعادة تشغيل" : fixtureMode ? "عينة" : "مستلم"}</span>
            <span className="rounded border border-[var(--border-hairline)] px-1.5 py-0.5 text-[9px] text-[var(--text-secondary)]" title={triage[alert.id]?.source === "server" ? `مسجَّل في الخدمة بواسطة ${triage[alert.id]?.actor}` : "حالة الجلسة"}>{TRIAGE_LABEL[triageState]}</span>
            <div className="flex min-w-18 items-center gap-1.5" title={`درجة النموذج ${Math.round(alert.confidence)} من 100 — غير معايرة`}><span className="h-1 w-11 overflow-hidden rounded-full bg-[var(--surface-3)]"><i className="block h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, alert.confidence))}%`, background: typeColor }} /></span><bdi className="instrument-num text-[10px] text-[var(--text-secondary)]" dir="ltr">{Math.round(alert.confidence)}%</bdi></div>
          </div>
        </div>
      })}
    </div>
    {alerts.length > WINDOW_SIZE && <div className="flex shrink-0 items-center justify-between border-t border-[var(--border-hairline)] px-3 py-2 text-[10px] text-[var(--text-tertiary)]"><button type="button" disabled={safePage === 0} onClick={() => setPage(safePage - 1)} className="flex min-h-8 items-center gap-1 text-[var(--signal)] disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><ChevronRight size={12} />الأحدث</button><bdi className="instrument-num" dir="ltr">{safePage * WINDOW_SIZE + 1}–{Math.min(alerts.length, (safePage + 1) * WINDOW_SIZE)} / {alerts.length}</bdi><button type="button" disabled={safePage === lastPage} onClick={() => setPage(safePage + 1)} className="flex min-h-8 items-center gap-1 text-[var(--signal)] disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-[var(--signal)]">الأقدم<ChevronLeft size={12} /></button></div>}
    <div className="shrink-0 border-t border-[var(--border-hairline)] px-3 py-2 text-[10px] text-[var(--text-tertiary)]"><span>{fixtureMode ? "بيانات معاينة محلية؛ لا تمثل رصداً حياً" : connectionStatus === "online" ? "القناة متصلة؛ حالة الكاميرا غير مؤكدة" : "حالة الرصد المباشر غير مؤكدة"}</span>{!fixtureMode && <span className="ms-2">· <bdi dir="ltr" className="instrument-num">a</bdi> {TRIAGE_ACTION_LABEL.acknowledge} · <bdi dir="ltr" className="instrument-num">c</bdi> {TRIAGE_ACTION_LABEL.resolve}</span>}{rejectedEnvelopes > 0 && <span role="status" className="ms-2 text-[var(--threat-medium)]">· رُفض {rejectedEnvelopes} إطاراً لا يطابق عقد التنبيه</span>}</div>
  </section>
})
