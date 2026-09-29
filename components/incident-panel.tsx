"use client"

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { Activity, AlertCircle, Camera, Check, ChevronDown, Clock3, Download, FileDown, Fingerprint, MapPin, ShieldAlert, SlidersHorizontal, Timer, UserRound, X } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"
import { SEVERITY_LABEL, TRIAGE_ACTION_LABEL, TRIAGE_ALLOWED, TRIAGE_LABEL, type CrossFilters, type TriageAction, type TriageState } from "@/lib/sentinel-selectors"
import { useSentinel, type ConnectionStatus } from "@/lib/sentinel-store"
import { incidentEvidenceFacts, parseEvidenceChainRecord, type EvidenceChainRecord } from "@/lib/local-report"
import { apiFetch } from "@/lib/api-auth"
import { useApiAccess } from "@/hooks/use-api-access"
import { useModalFocus } from "@/hooks/use-modal-focus"
import { IncidentReplay, type EvidenceStatus } from "@/components/incident-replay"
import { InstrumentValue } from "@/components/shell/primitives"
import { formatTime24 } from "@/components/shell/locale"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const MAX_POLL_ATTEMPTS = 20
const POLL_INTERVAL_MS = 1_500
const SETTING_DEBOUNCE_MS = 400
type DownloadState = "idle" | "working" | "done" | "error"
type Message = { text: string; kind: "success" | "error" | "info" }

type IncidentPanelProps = {
  alert: LiveAlert | null
  filters?: CrossFilters
  onFiltersChange?: (filters: CrossFilters) => void
  privacyMode?: boolean
  fixtureMode?: boolean
  connectionStatus?: ConnectionStatus
}

const TYPE_LABEL = { Weapon: "رصد سلاح", Violence: "رصد اعتداء" }
const SEVERITY_CLASS = {
  critical: "border-[var(--threat-critical)] text-[var(--threat-critical)]",
  high: "border-[var(--threat-high)] text-[var(--threat-high)]",
  medium: "border-[var(--threat-medium)] text-[var(--threat-medium)]",
}
const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function Fact({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return <div className="min-w-0 rounded-md border border-[var(--border-hairline)] bg-[var(--surface-2)] p-3">
    <div className="mb-1 flex items-center gap-1.5 text-[10px] text-[var(--text-tertiary)]">{icon}{label}</div>
    <div className="truncate text-xs font-medium text-[var(--text-primary)]">{children}</div>
  </div>
}

function Metric({ label, value, tone }: { label: string; value: number | null; tone: string }) {
  return <div className="space-y-1.5">
    <div className="flex items-center justify-between gap-2 text-[11px]"><span className="text-[var(--text-secondary)]">{label}</span><InstrumentValue value={value === null ? "غير متوفر" : value.toFixed(1) + "%"} className="text-[var(--text-primary)]" /></div>
    <div className="h-1.5 overflow-hidden rounded bg-[var(--surface-3)]"><div className="h-full rounded" style={{ width: String(value ?? 0) + "%", backgroundColor: tone }} /></div>
  </div>
}

function Setting({ label, note, value, min, max, step, unit, busy, disabled, onChange }: {
  label: string; note: string; value: number; min: number; max: number; step: number; unit: string
  busy: boolean; disabled: boolean; onChange: (value: number) => void
}) {
  return <label className="block space-y-2 rounded-md border border-[var(--border-hairline)] bg-[var(--surface-2)] p-3">
    <span className="flex items-center justify-between gap-2 text-xs"><span className="text-[var(--text-primary)]">{label}</span><InstrumentValue value={busy ? "جارٍ الحفظ…" : String(value) + unit} className="text-[var(--signal)]" /></span>
    <input type="range" min={min} max={max} step={step} value={value} disabled={disabled || busy} onChange={(event) => onChange(Number(event.target.value))} className="w-full accent-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40" />
    <span className="block text-[10px] leading-5 text-[var(--text-tertiary)]">{note}</span>
  </label>
}

export function IncidentPanel({ alert, filters, onFiltersChange, privacyMode = false, fixtureMode = false, connectionStatus = "offline" }: IncidentPanelProps) {
  const [evidenceState, setEvidenceState] = useState<DownloadState>("idle")
  const [reportState, setReportState] = useState<DownloadState>("idle")
  const [replayStatus, setReplayStatus] = useState<EvidenceStatus>("unavailable")
  const [chainState, setChainState] = useState<"loading" | "ready" | "unavailable" | "error">("unavailable")
  const [chainRecord, setChainRecord] = useState<EvidenceChainRecord | null>(null)
  const [chainRefresh, setChainRefresh] = useState(0)
  const [message, setMessage] = useState<Message | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [threshold, setThreshold] = useState(50)
  const [cooldown, setCooldown] = useState(60)
  const [thresholdBusy, setThresholdBusy] = useState(false)
  const [cooldownBusy, setCooldownBusy] = useState(false)
  const thresholdTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cooldownTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const facts = alert ? incidentEvidenceFacts(alert) : null
  const latencyLabel = facts?.latencyMs === null || facts?.latencyMs === undefined ? "غير متوفر" : facts.latencyMs.toFixed(0) + " ms"
  const alertTime = alert && Number.isFinite(Date.parse(alert.isoTime)) ? formatTime24(alert.isoTime) : alert?.timestamp || "غير متوفر"
  const confidenceLabel = alert && Number.isFinite(alert.confidence) && alert.confidence >= 0 && alert.confidence <= 100 ? alert.confidence.toFixed(1) + "%" : "غير متوفر"
  const face = alert?.faceSummary
  const faceTotal = typeof face?.totalFaces === "number" && Number.isFinite(face.totalFaces) && face.totalFaces >= 0 ? face.totalFaces : null
  const faceUnknown = typeof face?.unknownCount === "number" && Number.isFinite(face.unknownCount) && face.unknownCount >= 0 ? face.unknownCount : null
  const faceKnown = typeof face?.recognizedCount === "number" && Number.isFinite(face.recognizedCount) && face.recognizedCount >= 0 ? face.recognizedCount : Array.isArray(face?.recognized) ? face.recognized.length : null
  const validId = Boolean(alert && /^[A-Za-z0-9_-]{1,128}$/.test(alert.id))
  const operational = !fixtureMode && !privacyMode && connectionStatus === "online" && validId
  const dialogRef = useRef<HTMLDivElement>(null)
  const { triage, recordTriage, hydrateTriage } = useSentinel()
  const { role } = useApiAccess()
  const [triageBusy, setTriageBusy] = useState(false)
  const triageRecord = alert ? triage[alert.id] : undefined
  const triageState: TriageState = triageRecord?.state ?? "new"
  const triageActions = TRIAGE_ALLOWED[triageState]
  useModalFocus(dialogRef, confirmOpen)

  useEffect(() => {
    return () => {
      if (thresholdTimer.current) clearTimeout(thresholdTimer.current)
      if (cooldownTimer.current) clearTimeout(cooldownTimer.current)
    }
  }, [])
  useEffect(() => {
    if (!alert || fixtureMode || connectionStatus !== "online" || !/^[A-Za-z0-9_-]{1,128}$/.test(alert.id)) return
    let active = true
    const load = async () => {
      setChainState("loading")
      try {
        const response = await apiFetch(API_BASE + "/evidence_chain/" + encodeURIComponent(alert.id))
        if (response.status === 404) { if (active) { setChainState("unavailable"); setChainRecord(null) }; return }
        if (!response.ok) throw new Error("ledger unavailable")
        const record = parseEvidenceChainRecord(await response.json(), alert.id)
        if (!record) throw new Error("invalid ledger record")
        if (active) { setChainRecord(record); setChainState("ready") }
      } catch { if (active) { setChainRecord(null); setChainState("error") } }
    }
    void load()
    return () => { active = false }
  }, [alert, fixtureMode, connectionStatus, chainRefresh])

  useEffect(() => {
    if (!alert || fixtureMode || connectionStatus !== "online" || !/^[A-Za-z0-9_-]{1,128}$/.test(alert.id)) return
    void hydrateTriage(alert.id)
  }, [alert, fixtureMode, connectionStatus, hydrateTriage])

  const applyTriage = async (action: TriageAction) => {
    if (!alert || triageBusy || role !== "admin") return
    setTriageBusy(true)
    const outcome = await recordTriage(alert.id, action, role ?? "غير معروف")
    setTriageBusy(false)
    setMessage(outcome === "rejected"
      ? { text: "الانتقال غير مسموح من الحالة الحالية.", kind: "error" }
      : outcome === "server"
        ? { text: "سُجّل الانتقال في خدمة الحوادث.", kind: "success" }
        : { text: "حالة الجلسة فقط: تعذّر تسجيل الانتقال في الخدمة.", kind: "info" })
  }

  const setFilter = (patch: Partial<CrossFilters>) => {
    if (filters && onFiltersChange) onFiltersChange({ ...filters, ...patch })
  }
  const saveBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 5_000)
  }
  const downloadEvidence = async () => {
    if (!alert || !operational || evidenceState === "working") return
    setEvidenceState("working")
    for (let attempt = 1; attempt <= MAX_POLL_ATTEMPTS; attempt++) {
      try {
        const response = await apiFetch(API_BASE + "/download_evidence/" + encodeURIComponent(alert.id))
        if (response.status === 202) {
          if (attempt === MAX_POLL_ATTEMPTS) break
          await sleep(POLL_INTERVAL_MS)
          continue
        }
        if (!response.ok) throw new Error("download failed")
        saveBlob(await response.blob(), alert.id + ".mp4")
        setEvidenceState("done")
        setMessage({ text: "حُفظ مقطع الدليل على جهازك.", kind: "success" })
        return
      } catch { break }
    }
    setEvidenceState("error")
    setMessage({ text: "تعذر تنزيل المقطع. تحقق من خدمة الأدلة وحاول مجدداً.", kind: "error" })
  }
  const downloadReport = async () => {
    if (!alert || !operational || reportState === "working") return
    setReportState("working")
    try {
      const reportPath = "/download_report/" + encodeURIComponent(alert.id)
      let response = await apiFetch(API_BASE + reportPath)
      if (response.status === 404 && role === "admin") {
        const generated = await apiFetch(API_BASE + "/reports/pdf/" + encodeURIComponent(alert.id), { method: "POST" })
        if (!generated.ok) throw new Error("generation failed")
        response = await apiFetch(API_BASE + reportPath)
      } else if (response.status === 404 && role !== "admin") {
        throw new Error("admin-required")
      }
      if (!response.ok) throw new Error("download failed")
      saveBlob(await response.blob(), alert.id + ".pdf")
      setReportState("done")
      setMessage({ text: "حُفظ تقرير الحادثة على جهازك.", kind: "success" })
    } catch (error) {
      setReportState("error")
      setMessage({ text: error instanceof Error && error.message === "admin-required"
        ? "لم يُنشأ ملف PDF بعد؛ اطلب من مسؤول إنشاء التقرير."
        : "تعذر تنزيل التقرير. تحقق من الخدمة أو صلاحية الوصول.", kind: "error" })
    }
  }
  const saveSetting = useCallback(async (key: "threshold" | "cooldown", value: number) => {
    const setBusy = key === "threshold" ? setThresholdBusy : setCooldownBusy
    setBusy(true)
    try {
      const response = await apiFetch(API_BASE + (key === "threshold" ? "/set_threshold" : "/set_cooldown"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(key === "threshold" ? { threshold: value / 100 } : { cooldown: value }),
      })
      if (!response.ok) throw new Error("setting failed")
      setMessage({ text: "أرسلت قيمة الضبط إلى الخدمة.", kind: "success" })
    } catch { setMessage({ text: "تعذر حفظ الضبط. القيمة الحالية في الخدمة غير معروفة.", kind: "error" }) }
    finally { setBusy(false) }
  }, [])
  const changeThreshold = (value: number) => {
    setThreshold(value)
    if (thresholdTimer.current) clearTimeout(thresholdTimer.current)
    thresholdTimer.current = setTimeout(() => void saveSetting("threshold", value), SETTING_DEBOUNCE_MS)
  }
  const changeCooldown = (value: number) => {
    setCooldown(value)
    if (cooldownTimer.current) clearTimeout(cooldownTimer.current)
    cooldownTimer.current = setTimeout(() => void saveSetting("cooldown", value), SETTING_DEBOUNCE_MS)
  }

  return <div className="min-w-0 space-y-4 p-4 md:p-5">
    {!alert ? <div className="flex min-h-[420px] flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-[var(--border-hairline)] bg-[var(--surface-1)] px-6 text-center">
      <div className="grid size-16 place-items-center rounded-full border border-[var(--border-hairline)] text-[var(--text-tertiary)]"><ShieldAlert size={27} /></div>
      <div><h2 className="text-base font-semibold">اختر تنبيهاً لفتح ملف الحادثة</h2><p className="mt-2 max-w-sm text-xs leading-6 text-[var(--text-secondary)]">تظهر هنا تفاصيل التنبيه والأدلة المسجلة ومؤشرات القرار عندما تتوفر.</p></div>
    </div> : <>
      <header className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0"><div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] text-[var(--text-tertiary)]"><span className="uppercase tracking-[.15em]">ملف الحادثة / 04</span><span>•</span><bdi className="instrument-num">{alert.id}</bdi></div><h2 className="text-xl font-semibold text-[var(--text-primary)] md:text-2xl">{TYPE_LABEL[alert.type]}</h2><p className="mt-1 text-xs text-[var(--text-secondary)]">مراجعة تنبيه مستلم؛ يتطلب التحقق البشري قبل اتخاذ قرار تشغيلي.</p></div>
          <button type="button" onClick={() => setFilter({ severity: filters?.severity === alert.severity ? undefined : alert.severity })} className={"rounded border px-3 py-1.5 text-xs font-semibold focus-visible:outline-2 focus-visible:outline-[var(--signal)] " + SEVERITY_CLASS[alert.severity]} aria-label={"تصفية حسب شدة " + SEVERITY_LABEL[alert.severity]}>{SEVERITY_LABEL[alert.severity]}</button>
        </div>
        {fixtureMode && <div className="mt-4 rounded border border-[var(--state-replay)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--state-replay)]">سجل تجريبي للمعاينة فقط · لا يرتبط بدليل أو إجراء تشغيلي</div>}
        {connectionStatus !== "online" && !fixtureMode && <div className="mt-4 rounded border border-[var(--border-hairline)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--state-offline)]">قناة التنبيهات غير متصلة حالياً؛ قد تكون بيانات هذه الحادثة قديمة.</div>}
        <div className="mt-4 grid grid-cols-2 gap-2 xl:grid-cols-4">
          <Fact icon={<Camera size={13} />} label="الكاميرا"><button type="button" onClick={() => setFilter({ cameraId: filters?.cameraId === alert.cameraId ? undefined : alert.cameraId })} className="text-[var(--signal)] underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><InstrumentValue value={alert.cameraId || "غير متوفر"} /></button></Fact>
          <Fact icon={<MapPin size={13} />} label="الموقع">{alert.location || "غير متوفر"}</Fact>
          <Fact icon={<Clock3 size={13} />} label="وقت التنبيه"><InstrumentValue value={alertTime} /></Fact>
          <Fact icon={<Timer size={13} />} label="كمون التنبيه"><InstrumentValue value={latencyLabel} /></Fact>
        </div>
        <button type="button" onClick={() => setFilter({ type: filters?.type === alert.type ? undefined : alert.type })} className="mt-3 inline-flex items-center gap-1 rounded border border-[var(--border-hairline)] px-2 py-1 text-[10px] text-[var(--cat-weapon)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]" style={{ color: alert.type === "Weapon" ? "var(--cat-weapon)" : "var(--cat-violence)" }}>{alert.type === "Weapon" ? "فئة: سلاح" : "فئة: اعتداء"} <span className="text-[var(--text-tertiary)]">· انقر للتصفية</span></button>
      </header>

      <section className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4" aria-label="حالة معالجة الحادثة">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">حالة المعالجة</h3>
          <span className="rounded border border-[var(--border-hairline)] bg-[var(--surface-2)] px-2 py-1 text-[11px] text-[var(--text-primary)]">{TRIAGE_LABEL[triageState]}</span>
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="نقل الحادثة إلى حالة أخرى">
          {triageActions.map((action) => <button key={action} type="button" disabled={triageBusy || fixtureMode || role !== "admin"} onClick={() => void applyTriage(action)} className="inline-flex min-h-9 items-center gap-1.5 rounded border border-[var(--border-hairline)] px-3 text-xs text-[var(--text-primary)] hover:border-[var(--signal)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40">{TRIAGE_ACTION_LABEL[action]}</button>)}
          {triageBusy && <span className="self-center text-[10px] text-[var(--text-tertiary)]" role="status">جارٍ تسجيل الانتقال…</span>}
        </div>
        <p className="mt-2 text-[10px] leading-5 text-[var(--text-tertiary)]">
          {fixtureMode ? "المعاينة التجريبية لا تسجل حالات معالجة."
            : role !== "admin" ? "وضع مشاهدة فقط؛ صلاحية المسؤول مطلوبة لتغيير حالة المعالجة."
              : !triageRecord ? "لا انتقال مسجَّل بعد؛ الحالة الابتدائية «جديد»."
              : triageRecord.source === "server"
                ? `آخر انتقال: ${TRIAGE_ACTION_LABEL[triageRecord.action]} بواسطة ${triageRecord.actor} في ${formatTime24(new Date(triageRecord.at).toISOString())}.`
                : "حالة الجلسة فقط: تعذّر تسجيل الانتقال في الخدمة (غير متصلة أو رفضت الطلب)."}
        </p>
        {!fixtureMode && <p className="mt-1 text-[10px] leading-5 text-[var(--text-tertiary)]">تُحفظ الحالة في عملية الخدمة الحالية فقط؛ إعادة التشغيل تُلغيها ولا تُقيد في سلسلة الأدلة.</p>}
        {triageRecord && triageRecord.history.length > 0 && <ul className="mt-3 space-y-1 border-t border-[var(--border-hairline)] pt-3 text-[10px] text-[var(--text-secondary)]">
          {triageRecord.history.slice(-5).map((entry) => <li key={`${entry.at}-${entry.action}`} className="flex items-center gap-1.5"><Activity size={11} className="text-[var(--signal)]" /><span>{TRIAGE_ACTION_LABEL[entry.action]}</span><span className="text-[var(--text-tertiary)]">· {entry.actor} ·</span><bdi className="instrument-num text-[var(--text-tertiary)]" dir="ltr">{formatTime24(new Date(entry.at).toISOString())}</bdi></li>)}
        </ul>}
      </section>

      {fixtureMode
        ? <div className="flex aspect-video min-h-[210px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[var(--border-hairline)] bg-[var(--surface-0)] px-5 text-center"><ShieldAlert size={27} className="text-[var(--state-replay)]" /><strong className="text-sm">لا يوجد دليل مصور للعينة التجريبية</strong><p className="max-w-sm text-xs leading-6 text-[var(--text-tertiary)]">توضح العينة شكل ملف الحادثة فقط. المقاطع والتقارير متاحة للحوادث الحقيقية عند حفظها في الخدمة.</p></div>
        : privacyMode ? <div className="flex aspect-video min-h-[210px] flex-col items-center justify-center gap-3 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-0)] px-5 text-center"><ShieldAlert size={27} className="text-[var(--text-tertiary)]" /><strong className="text-sm">الدليل المصور محجوب بوضع الخصوصية</strong><p className="max-w-sm text-xs leading-6 text-[var(--text-tertiary)]">أوقف وضع الخصوصية لمراجعة المقطع أو تنزيله.</p></div>
          : connectionStatus !== "online" ? <div className="flex aspect-video min-h-[210px] flex-col items-center justify-center gap-3 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-0)] px-5 text-center"><ShieldAlert size={27} className="text-[var(--state-offline)]" /><strong className="text-sm">الدليل المصور غير متاح حالياً</strong><p className="max-w-sm text-xs leading-6 text-[var(--text-tertiary)]">قناة التنبيهات غير متصلة؛ لا يمكن التحقق من المقطع المحفوظ حتى يعود الاتصال.</p></div>
          : <IncidentReplay key={alert.id} alertId={alert.id} threatType={alert.type === "Weapon" ? "weapon" : "violence"} confidence={alert.confidence} location={alert.location} timestamp={alertTime} onStatusChange={setReplayStatus} />}

      <div className="grid gap-3 xl:grid-cols-[1.25fr_1fr]">
        <section className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4">
          <div className="mb-4 flex items-center justify-between"><h3 className="text-sm font-semibold">تفصيل مؤشرات الكشف</h3><span className="text-[10px] text-[var(--text-tertiary)]">من بيانات التنبيه</span></div>
          <div className="space-y-3"><Metric label="الدمج" value={facts?.fusion ?? null} tone="var(--signal)" /><Metric label="السلاح" value={facts?.weapon ?? null} tone="var(--cat-weapon)" /><Metric label="الحركة" value={facts?.motion ?? null} tone="var(--cat-violence)" /></div>
          <p className="mt-3 border-t border-[var(--border-hairline)] pt-3 text-[10px] text-[var(--text-tertiary)]">درجة النموذج المبلغ عنها: <InstrumentValue value={confidenceLabel} className="text-[var(--text-primary)]" /> — مقياس 0–100 غير معاير، وليست احتمالاً ولا دقة للنظام. التصنيف التشغيلي يعتمد على الخطورة.</p>
        </section>
        <section className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4">
          <div className="mb-3 flex items-center justify-between gap-2"><h3 className="flex items-center gap-2 text-sm font-semibold"><Fingerprint size={16} className="text-[var(--signal)]" />سجل الدليل</h3>{!fixtureMode && <button type="button" onClick={() => setChainRefresh((value) => value + 1)} className="text-[10px] text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]">تحديث</button>}</div>
          <dl className="space-y-2 text-[11px]"><div className="flex justify-between gap-2"><dt className="text-[var(--text-tertiary)]">معرّف التنبيه</dt><dd><bdi className="instrument-num">{alert.id}</bdi></dd></div><div className="flex justify-between gap-2"><dt className="text-[var(--text-tertiary)]">المقطع</dt><dd>{fixtureMode ? "عينة بلا دليل" : replayStatus === "ready" ? "متاح للمراجعة" : replayStatus === "loading" ? "جارٍ التحقق" : replayStatus === "error" || connectionStatus !== "online" ? "تعذر التحقق" : "غير متوفر"}</dd></div><div className="flex justify-between gap-2"><dt className="text-[var(--text-tertiary)]">قيد السلسلة</dt><dd>{fixtureMode ? "غير متوفر" : chainState === "loading" ? "جارٍ التحقق" : chainState === "ready" ? "أعادته خدمة الأدلة" : chainState === "error" || connectionStatus !== "online" ? "تعذر التحقق" : "غير متوفر"}</dd></div></dl>
          {chainRecord && chainState === "ready" ? <div className="mt-3 space-y-2 border-t border-[var(--border-hairline)] pt-3 text-[10px]"><p className="text-[var(--text-tertiary)]">وقت تسجيل القيد: <bdi className="instrument-num text-[var(--text-primary)]">{chainRecord.timestamp}</bdi></p><p className="text-[var(--text-tertiary)]">بصمة المقطع <InstrumentValue value={chainRecord.clipSha256 ?? "غير متوفر"} className="block break-all text-[var(--text-primary)]" /></p><p className="text-[var(--text-tertiary)]">بصمة القيد <bdi className="instrument-num block break-all text-[var(--text-primary)]">{chainRecord.currentHash}</bdi></p><p className="text-[var(--text-tertiary)]">القيد السابق <bdi className="instrument-num block break-all text-[var(--text-primary)]">{chainRecord.prevHash}</bdi></p></div>
            : <div className="mt-3 border-t border-[var(--border-hairline)] pt-3 text-[10px] text-[var(--text-tertiary)]">{fixtureMode ? "لا يوجد قيد للعينة التجريبية." : chainState === "error" ? "تعذر جلب القيد؛ لا يمكن تأكيد حالة السلسلة هنا." : "لم توفر الخدمة قيداً لهذه الحادثة بعد."}</div>}
        </section>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <section className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4">
          <h3 className="mb-2 text-sm font-semibold">تسميات السلاح</h3>
          {facts && facts.weaponLabels.length > 0 ? <div className="flex flex-wrap gap-1.5">{facts.weaponLabels.map((label) => <bdi key={label} className="rounded border border-[var(--cat-weapon)] px-2 py-1 text-[10px] text-[var(--cat-weapon)]">{label}</bdi>)}</div> : <p className="text-xs text-[var(--text-tertiary)]">غير متوفر في بيانات التنبيه</p>}
        </section>
        <section className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold"><UserRound size={15} />ملخص الوجوه</h3>
          {privacyMode ? <p className="text-xs text-[var(--text-tertiary)]">البيانات محجوبة وفق وضع الخصوصية.</p>
            : !face?.enabled ? <p className="text-xs text-[var(--text-tertiary)]">غير متوفر في بيانات التنبيه</p>
              : <div className="space-y-1 text-xs text-[var(--text-secondary)]"><p>الوجوه المرصودة: <InstrumentValue value={faceTotal ?? "غير متوفر"} /></p><p>غير المعروفة: <InstrumentValue value={faceUnknown ?? "غير متوفر"} /></p><p>المعروفة: <InstrumentValue value={faceKnown ?? "غير متوفر"} /></p>{face.identityLabelingEnabled === false && <p className="text-[10px] text-[var(--text-tertiary)]">تسمية الهوية معطلة.</p>}</div>}
        </section>
      </div>

      <section className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4">
        <h3 className="mb-3 text-sm font-semibold">الأدلة والإجراءات</h3>
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={!operational || evidenceState === "working"} onClick={() => void downloadEvidence()} className="inline-flex items-center gap-2 rounded bg-[var(--signal)] px-3 py-2 text-xs font-semibold text-[var(--signal-contrast)] hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)] disabled:opacity-40"><Download size={14} />{evidenceState === "working" ? "جارٍ تجهيز المقطع…" : evidenceState === "done" ? "حُفظ المقطع" : "تنزيل الدليل"}</button>
          <button type="button" disabled={!operational || reportState === "working"} onClick={() => void downloadReport()} className="inline-flex items-center gap-2 rounded border border-[var(--border-hairline)] px-3 py-2 text-xs text-[var(--text-primary)] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40"><FileDown size={14} />{reportState === "working" ? "جارٍ تجهيز التقرير…" : "تنزيل تقرير PDF"}</button>
          <button type="button" disabled={fixtureMode} onClick={() => setConfirmOpen(true)} className="inline-flex items-center gap-2 rounded border border-[var(--threat-critical)] px-3 py-2 text-xs text-[var(--threat-critical)] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40"><ShieldAlert size={14} />مراجعة التصعيد</button>
          <button type="button" disabled={fixtureMode} onClick={() => setMessage({ text: "لا توجد واجهة لحفظ حكم الإنذار الكاذب؛ دوّن قرارك في نظام الإجراءات المعتمد.", kind: "info" })} className="inline-flex items-center gap-2 rounded border border-[var(--border-hairline)] px-3 py-2 text-xs text-[var(--text-secondary)] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40"><X size={14} />مراجعة إنذار كاذب</button>
        </div>
        {fixtureMode && <p className="mt-2 text-[10px] text-[var(--state-replay)]">الإجراءات والتنزيلات معطلة في المعاينة التجريبية.</p>}
        {privacyMode && !fixtureMode && <p className="mt-2 text-[10px] text-[var(--text-tertiary)]">التنزيلات معطلة ما دام وضع الخصوصية مفعلاً.</p>}
      </section>
    </>}

    <details className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] p-4">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-xs font-semibold focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><SlidersHorizontal size={15} className="text-[var(--signal)]" />ضبط سياسة التنبيه <ChevronDown size={14} className="ms-auto text-[var(--text-tertiary)]" /></summary>
      <p className="my-3 text-[10px] leading-5 text-[var(--text-tertiary)]">القيم أدناه مدخلات مقترحة حتى تُرسل إلى الخدمة؛ لا تعرض الإعداد الحالي المخزن.</p>
      <div className="grid gap-2 md:grid-cols-2"><Setting label="حد الكشف" note="10% أكثر استجابة · 95% أكثر تحفظاً" value={threshold} min={10} max={95} step={1} unit="%" busy={thresholdBusy} disabled={fixtureMode} onChange={changeThreshold} /><Setting label="فترة كبح التنبيه" note="من 15 إلى 120 ثانية" value={cooldown} min={15} max={120} step={5} unit="s" busy={cooldownBusy} disabled={fixtureMode} onChange={changeCooldown} /></div>
    </details>
    {message && <div role="status" className={"flex items-start gap-2 rounded border px-3 py-2 text-xs " + (message.kind === "error" ? "border-[var(--threat-critical)] text-[var(--threat-critical)]" : message.kind === "success" ? "border-[var(--signal)] text-[var(--signal)]" : "border-[var(--border-hairline)] text-[var(--text-secondary)]")}>{message.kind === "error" ? <AlertCircle size={14} /> : <Check size={14} />}<span className="flex-1">{message.text}</span><button type="button" onClick={() => setMessage(null)} aria-label="إغلاق الإشعار" className="focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><X size={14} /></button></div>}
    {confirmOpen && <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="dispatch-title" className="fixed inset-0 z-[200] grid place-items-center bg-[var(--surface-0)]/85 p-4 focus-visible:outline-none" onKeyDown={(event) => { if (event.key === "Escape") setConfirmOpen(false) }}>
      <div className="w-full max-w-md rounded-lg border border-[var(--threat-critical)] bg-[var(--surface-1)] p-5 shadow-2xl"><h3 id="dispatch-title" className="text-base font-semibold">مراجعة التصعيد</h3><p className="mt-3 text-xs leading-6 text-[var(--text-secondary)]">لا توجد خدمة إرسال فريق أمني مرتبطة بهذا الزر. استخدم قناة الاستجابة المعتمدة، ثم وثّق القرار خارج هذه الواجهة.</p><div className="mt-4 flex justify-end"><button type="button" autoFocus onClick={() => setConfirmOpen(false)} className="rounded bg-[var(--signal)] px-4 py-2 text-xs font-semibold text-[var(--signal-contrast)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)]">فهمت</button></div></div>
    </div>}
  </div>
}
