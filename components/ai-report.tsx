"use client"

import { useCallback, useEffect, useState, type ReactNode } from "react"
import { AlertCircle, Copy, Download, FileSearch, RefreshCw, Sparkles } from "lucide-react"
import { apiFetch } from "@/lib/api-auth"
import { parseLocalEvidenceReport } from "@/lib/local-report"
import { formatDateTime24 } from "@/components/shell/locale"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const PANEL = "rounded-[var(--radius-panel)] border border-[var(--border-hairline)] bg-[var(--surface-1)]"
const ACTION = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-[var(--border-hairline)] px-3 text-xs text-[var(--text-secondary)] hover:border-[var(--signal)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-50"

interface ReportData {
  executive_summary?: string
  incident_classification?: string
  source_and_evidence?: string
  confidence_analysis?: string
  timeline?: string | string[]
  behavioral_interpretation?: string
  risk_assessment?: string
  operator_actions?: string | string[]
  demo_explanation?: string
  limitations?: string | string[]
  final_verdict?: string
  incident_type?: string
  severity_assessment?: string
  confidence_interpretation?: string
  camera_source?: string
  observed_evidence?: string
  recommended_actions?: string | string[]
  demo_notes_for_graduation_committee?: string
  raw?: boolean
}
interface ReportEnvelope { alert_id: string; generated_at: string; model: string; report: ReportData }
function parseReportEnvelope(value: unknown, alertId: string): ReportEnvelope | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null
  const data = value as Record<string, unknown>
  if (data.alert_id !== alertId || typeof data.generated_at !== "string" || typeof data.model !== "string"
    || !data.report || typeof data.report !== "object" || Array.isArray(data.report)) return null
  return data as unknown as ReportEnvelope
}
type RemoteState =
  | { status: "idle" | "checking" | "missing" | "generating" }
  | { status: "ready"; data: ReportEnvelope }
  | { status: "error"; message: string }
type LocalState =
  | { status: "idle" | "loading" | "missing" }
  | { status: "ready"; report: string }
  | { status: "error"; message: string }

function saveText(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }))
  try { const link = document.createElement("a"); link.href = url; link.download = name.replace(/[^a-zA-Z0-9._-]/g, "_"); link.click() }
  finally { window.setTimeout(() => URL.revokeObjectURL(url), 0) }
}
function lines(value: string | string[] | undefined): string[] {
  return value === undefined ? [] : Array.isArray(value) ? value.map(String).filter(Boolean) : [String(value)]
}
function ReportField({ label, value }: { label: string; value?: string | string[] }) {
  const content = lines(value)
  if (!content.length) return null
  return <section className="border-t border-[var(--border-hairline)] py-4 first:border-0 first:pt-0"><h4 className="mb-2 text-[11px] font-semibold text-[var(--signal)]">{label}</h4>{content.length === 1 ? <p className="whitespace-pre-wrap text-[13px] leading-7 text-[var(--text-primary)]">{content[0]}</p> : <ul className="list-inside list-disc space-y-1 text-[13px] leading-7 text-[var(--text-primary)]">{content.map((item, index) => <li key={index}>{item}</li>)}</ul>}</section>
}
function StateNotice({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <div role={error ? "alert" : "status"} className={`${PANEL} flex items-start gap-3 p-5 text-xs leading-6 ${error ? "text-[var(--threat-high)]" : "text-[var(--text-secondary)]"}`}>{error ? <AlertCircle size={18} className="mt-0.5 shrink-0" /> : <FileSearch size={18} className="mt-0.5 shrink-0" />}<div>{children}</div></div>
}

function LocalArabicSummary({ alertId }: { alertId?: string }) {
  const [state, setState] = useState<LocalState>({ status: "idle" })
  const [refresh, setRefresh] = useState(0)
  const [copyStatus, setCopyStatus] = useState("")
  useEffect(() => {
    if (!alertId) return
    const controller = new AbortController()
    setState({ status: "loading" })
    apiFetch(`${API_BASE}/reports/local/${encodeURIComponent(alertId)}`, { signal: controller.signal })
      .then(async response => {
        if (response.status === 404) { if (!controller.signal.aborted) setState({ status: "missing" }); return }
        if (response.status === 401 || response.status === 403) { if (!controller.signal.aborted) setState({ status: "error", message: "يلزم وصول القارئ لعرض هذا الملخص." }); return }
        if (!response.ok) throw new Error("report unavailable")
        const report = parseLocalEvidenceReport(await response.json(), alertId)
        if (!report) throw new Error("invalid report")
        if (!controller.signal.aborted) setState({ status: "ready", report: report.report })
      })
      .catch(() => { if (!controller.signal.aborted) setState({ status: "error", message: "تعذر تحميل الملخص المحلي. تحقق من اتصال الخادم ثم أعد المحاولة." }) })
    return () => controller.abort()
  }, [alertId, refresh])
  const copy = async () => {
    if (state.status !== "ready") return
    try { await navigator.clipboard.writeText(state.report); setCopyStatus("نُسخ الملخص") }
    catch { setCopyStatus("تعذر النسخ") }
  }
  const readyReport = state.status === "ready" ? state.report : null
  return <section className={`${PANEL} overflow-hidden`} aria-label="الملخص المحلي للوقائع">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border-hairline)] p-5"><div><span className="inline-flex items-center gap-2 text-[10px] font-semibold text-[var(--signal)]"><FileSearch size={15} />تقرير محلي · حقائق السجل</span><h3 className="mt-2 text-lg font-semibold">ملخص الوقائع بالعربية</h3><p className="mt-1 text-xs leading-6 text-[var(--text-secondary)]">نص محفوظ من بيانات الحادثة. لا يتضمن تفسير صور أو استنتاجاً من نموذج لغوي.</p></div><span className="rounded border border-[var(--border-hairline)] px-2 py-1 text-[10px] text-[var(--text-tertiary)]">محلي / وقائع</span></div>
    <div className="p-5">{!alertId && <StateNotice>اختر حادثة من القائمة لقراءة ملخصها المحفوظ.</StateNotice>}{state.status === "loading" && <StateNotice>جارٍ تحميل الملخص المحفوظ…</StateNotice>}{state.status === "missing" && <StateNotice>لا يوجد ملخص محلي محفوظ لهذه الحادثة حتى الآن.</StateNotice>}{state.status === "error" && <StateNotice error>{state.message}</StateNotice>}{state.status === "ready" && <div className="border-s-2 border-[var(--signal)] bg-[var(--surface-2)] px-5 py-4"><pre dir="rtl" lang="ar" className="whitespace-pre-wrap break-words font-sans text-[13px] leading-8 text-[var(--text-primary)]">{state.report}</pre></div>}
      {alertId && <div className="mt-4 flex flex-wrap items-center gap-2"><button className={ACTION} onClick={() => setRefresh(value => value + 1)} disabled={state.status === "loading"}><RefreshCw size={14} />إعادة التحميل</button>{readyReport && <><button className={ACTION} onClick={() => void copy()}><Copy size={14} />نسخ الملخص</button><button className={ACTION} onClick={() => saveText(`sentinel-${alertId}-local.txt`, readyReport)}><Download size={14} />تصدير نص</button></>}{copyStatus && <span role="status" className="text-xs text-[var(--text-secondary)]">{copyStatus}</span>}</div>}</div>
  </section>
}

export function AiReport({ alertId }: { alertId: string | undefined }) {
  const [state, setState] = useState<RemoteState>({ status: "idle" })
  const [missingKey, setMissingKey] = useState<boolean | null>(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    apiFetch(`${API_BASE}/reports/deepseek/status`).then(response => response.ok ? response.json() : null).then(data => setMissingKey(data ? !data.apiKeyPresent : null)).catch(() => setMissingKey(null))
  }, [])
  useEffect(() => {
    if (!alertId) return
    const controller = new AbortController()
    setState({ status: "checking" })
    apiFetch(`${API_BASE}/reports/deepseek/${encodeURIComponent(alertId)}`, { signal: controller.signal })
      .then(async response => {
        if (response.status === 404) { if (!controller.signal.aborted) setState({ status: "missing" }); return }
        if (!response.ok) throw new Error("report unavailable")
        const data = parseReportEnvelope(await response.json(), alertId)
        if (!data) throw new Error("invalid report")
        if (!controller.signal.aborted) setState({ status: "ready", data })
      })
      .catch(() => { if (!controller.signal.aborted) setState({ status: "error", message: "تعذر تحميل التقرير عبر الخادم." }) })
    return () => controller.abort()
  }, [alertId])
  const generate = useCallback(async (force = false) => {
    if (!alertId) return
    setState({ status: "generating" })
    try {
      const response = await apiFetch(`${API_BASE}/reports/deepseek/${encodeURIComponent(alertId)}?force=${force}`, { method: "POST" })
      if (!response.ok) { setState({ status: "error", message: response.status === 401 || response.status === 403 ? "يلزم وصول مشغّل صالح لإنشاء التقرير." : "تعذر إنشاء التقرير. تحقق من إعداد الخدمة الخارجية واتصال الخادم." }); return }
      const data = parseReportEnvelope(await response.json(), alertId)
      if (!data) throw new Error("invalid report")
      setState({ status: "ready", data })
    } catch { setState({ status: "error", message: "تعذر الاتصال بالخادم لإنشاء التقرير." }) }
  }, [alertId])
  const copy = async () => {
    if (state.status !== "ready") return
    try { await navigator.clipboard.writeText(JSON.stringify(state.data.report, null, 2)); setCopied(true); window.setTimeout(() => setCopied(false), 2000) }
    catch { setCopied(false) }
  }
  const report = state.status === "ready" ? state.data.report : null
  return <div className="space-y-3"><LocalArabicSummary key={alertId ?? "none"} alertId={alertId} /><details className={PANEL}><summary className="cursor-pointer px-5 py-4 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><span className="inline-flex items-center gap-2"><Sparkles size={16} className="text-[var(--cat-violence)]" />تقرير النموذج الاختياري</span></summary><div className="space-y-4 border-t border-[var(--border-hairline)] p-5"><p className="border-s-2 border-[var(--cat-violence)] ps-3 text-xs leading-6 text-[var(--text-secondary)]">صياغة آلية من بيانات التنبيه، وليست حقيقة مثبتة أو قراءة مباشرة للفيديو. إنشاء تقرير جديد يرسل بيانات الحادثة إلى <bdi dir="ltr">DeepSeek via OpenRouter</bdi> ويتطلب اتصالاً بالشبكة.</p>
    {missingKey === true && <StateNotice error>مفتاح الخدمة الخارجية غير مهيأ على الخادم.</StateNotice>}
    {state.status === "idle" && <StateNotice>اختر حادثة لقراءة التقرير المرتبط بها.</StateNotice>}
    {state.status === "checking" && <StateNotice>جارٍ البحث عن تقرير محفوظ…</StateNotice>}
    {state.status === "missing" && <div className="space-y-3"><StateNotice>لا يوجد تقرير نموذج محفوظ لهذه الحادثة.</StateNotice><button className={ACTION} onClick={() => void generate()} disabled={missingKey === true}><Sparkles size={14} />إنشاء تقرير</button></div>}
    {state.status === "generating" && <StateNotice>جارٍ إنشاء التقرير عبر الخدمة الخارجية…</StateNotice>}
    {state.status === "error" && <div className="space-y-3"><StateNotice error>{state.message}</StateNotice>{alertId && <button className={ACTION} onClick={() => void generate()}><RefreshCw size={14} />إعادة المحاولة</button>}</div>}
    {state.status === "ready" && report && <><div className="flex flex-wrap items-center gap-2"><button className={ACTION} onClick={() => void generate(true)}><RefreshCw size={14} />إعادة الإنشاء</button><button className={ACTION} onClick={() => void copy()}><Copy size={14} />{copied ? "نُسخ التقرير" : "نسخ التقرير"}</button><button className={ACTION} onClick={() => saveText(`sentinel-${alertId}-model.json`, JSON.stringify(report, null, 2))}><Download size={14} />تصدير نص</button><span className="ms-auto text-[10px] text-[var(--text-tertiary)]"><bdi dir="ltr" className="instrument-num">{state.data.model}</bdi> · {Number.isNaN(Date.parse(state.data.generated_at)) ? "وقت غير متاح" : formatDateTime24(state.data.generated_at)}</span></div><div className="rounded border border-[var(--border-hairline)] bg-[var(--surface-2)] p-5">{report.raw && <p className="mb-4 text-xs text-[var(--threat-high)]">أعاد النموذج نصاً غير منظم؛ يُعرض كما ورد.</p>}<ReportField label="الملخص التنفيذي · صياغة النموذج" value={report.executive_summary} /><ReportField label="تصنيف الحادثة" value={report.incident_classification ?? report.incident_type} /><ReportField label="تقييم الخطورة" value={report.severity_assessment} /><ReportField label="المصدر والأدلة المذكورة" value={report.source_and_evidence ?? report.observed_evidence ?? report.camera_source} /><ReportField label="تحليل الثقة" value={report.confidence_analysis ?? report.confidence_interpretation} /><ReportField label="التسلسل الزمني" value={report.timeline} /><ReportField label="تفسير السلوك" value={report.behavioral_interpretation} /><ReportField label="تقييم المخاطر" value={report.risk_assessment} /><ReportField label="إجراءات مقترحة للمشغّل" value={report.operator_actions ?? report.recommended_actions} /><ReportField label="القيود" value={report.limitations} /><ReportField label="الخلاصة الآلية" value={report.final_verdict} /><ReportField label="ملاحظات العرض التجريبي" value={report.demo_explanation ?? report.demo_notes_for_graduation_committee} /></div><p className="text-[10px] leading-5 text-[var(--text-tertiary)]">المصدر: تقرير مولّد من بيانات التنبيه عبر خدمة خارجية. راجع السجل والأدلة الأصلية قبل اتخاذ إجراء.</p></>}</div></details></div>
}
