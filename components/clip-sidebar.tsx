"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Camera, Clock3, Download, Film, RefreshCw, X } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"
import type { ConnectionStatus } from "@/lib/sentinel-store"
import type { CrossFilters } from "@/lib/sentinel-selectors"
import { apiFetch } from "@/lib/api-auth"
import { useModalFocus } from "@/hooks/use-modal-focus"
import { IncidentReplay } from "@/components/incident-replay"
import { InstrumentValue } from "@/components/shell/primitives"
import { formatTime24, normalizeLatinDigits } from "@/components/shell/locale"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const POLL_MS = 5_000
interface FolderClip {
  alertId: string
  clipUrl: string
  timestamp: string | null
  cameraId: string | null
  type: string
  confidence: number | null
  severity: string | null
  size: number
  mtime: number
}
interface ClipSidebarProps {
  alerts: LiveAlert[]
  selectedAlertId?: string | null
  selectedAlert?: LiveAlert | null
  onSelectAlert: (alert: LiveAlert) => void
  onDeleteClip?: (alertId: string) => void
  fixtureMode?: boolean
  connectionStatus?: ConnectionStatus
  filters?: CrossFilters
  privacyMode?: boolean
}

function parseClips(value: unknown): FolderClip[] {
  if (!value || typeof value !== "object" || !("clips" in value) || !Array.isArray(value.clips)) return []
  return value.clips.flatMap((item: unknown): FolderClip[] => {
    if (!item || typeof item !== "object") return []
    const clip = item as Record<string, unknown>
    if (typeof clip.alertId !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(clip.alertId)
      || clip.clipUrl !== "/clips/" + clip.alertId || typeof clip.size !== "number" || !Number.isFinite(clip.size) || clip.size < 0
      || typeof clip.mtime !== "number" || !Number.isFinite(clip.mtime) || clip.mtime < 0) return []
    return [{
      alertId: clip.alertId, clipUrl: clip.clipUrl, size: clip.size, mtime: clip.mtime,
      timestamp: typeof clip.timestamp === "string" ? clip.timestamp : null,
      cameraId: typeof clip.cameraId === "string" ? clip.cameraId : null,
      type: typeof clip.type === "string" ? clip.type : "unknown",
      confidence: typeof clip.confidence === "number" && Number.isFinite(clip.confidence) && clip.confidence >= 0 && clip.confidence <= 100 ? clip.confidence : null,
      severity: ["critical", "high", "medium"].includes(String(clip.severity)) ? String(clip.severity) : null,
    }]
  })
}

function formatSize(bytes: number) {
  return bytes < 1024 * 1024 ? String(Math.round(bytes / 1024)) + " KB" : (bytes / (1024 * 1024)).toFixed(1) + " MB"
}

function clipTime(clip: FolderClip, alert?: LiveAlert): string {
  const timestamp = alert?.isoTime ?? clip.timestamp
  if (!timestamp) return "غير متوفر"
  return Number.isFinite(Date.parse(timestamp)) ? formatTime24(timestamp) : normalizeLatinDigits(timestamp)
}

export function ClipSidebar({ alerts, selectedAlertId, selectedAlert, onSelectAlert, fixtureMode = false, connectionStatus = "offline", filters, privacyMode = false }: ClipSidebarProps) {
  const [clips, setClips] = useState<FolderClip[]>([])
  const [status, setStatus] = useState<"loading" | "ready" | "error">(fixtureMode ? "ready" : connectionStatus === "online" ? "loading" : "error")
  const [modalClip, setModalClip] = useState<FolderClip | null>(null)
  const modalRef = useRef<HTMLDivElement>(null)
  useModalFocus(modalRef, Boolean(modalClip))
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [downloadError, setDownloadError] = useState(false)
  const alertMap = useMemo(() => new Map(alerts.map((alert) => [alert.id, alert])), [alerts])
  const related = useMemo(() => clips.filter((clip) => {
    const alert = alertMap.get(clip.alertId)
    const camera = alert?.cameraId ?? clip.cameraId
    const type = alert?.type ?? (clip.type === "Weapon Detection" ? "Weapon" : clip.type)
    const severity = alert?.severity ?? clip.severity
    const confidence = alert?.confidence ?? clip.confidence
    const time = alert ? Date.parse(alert.isoTime) : clip.mtime * 1000
    const rangeMs = filters?.range === "15m" ? 15 * 60_000 : filters?.range === "1h" ? 60 * 60_000 : filters?.range === "24h" ? 24 * 60 * 60_000 : null
    if (filters?.cameraId && camera !== filters.cameraId) return false
    if (filters?.type && type !== filters.type) return false
    if (filters?.severity && severity !== filters.severity) return false
    if (filters?.confidenceBand !== undefined && (confidence === null || confidence === undefined || Math.min(4, Math.floor(confidence / 20)) !== filters.confidenceBand)) return false
    if (rangeMs !== null && (!Number.isFinite(time) || time < Date.now() - rangeMs || time > Date.now())) return false
    if (!selectedAlert) return true
    return clip.alertId === selectedAlert.id || camera === selectedAlert.cameraId || type === selectedAlert.type
  }), [clips, alertMap, selectedAlert, filters])
  const fetchClips = useCallback(async () => {
    if (fixtureMode) return
    try {
      const response = await apiFetch(API_BASE + "/api/clips/list")
      if (!response.ok) throw new Error("unavailable")
      const data: unknown = await response.json()
      setClips(parseClips(data))
      setStatus("ready")
    } catch { setStatus("error") }
  }, [fixtureMode])
  useEffect(() => {
    if (fixtureMode || connectionStatus !== "online") return
    void fetchClips()
    const timer = setInterval(() => void fetchClips(), POLL_MS)
    return () => clearInterval(timer)
  }, [fetchClips, fixtureMode, connectionStatus])
  useEffect(() => {
    if (!modalClip) return
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setModalClip(null) }
    window.addEventListener("keydown", close)
    return () => window.removeEventListener("keydown", close)
  }, [modalClip])
  const download = async (clip: FolderClip) => {
    if (downloadBusy || privacyMode) return
    setDownloadBusy(true)
    setDownloadError(false)
    try {
      const response = await apiFetch(API_BASE + "/clips/" + encodeURIComponent(clip.alertId))
      if (!response.ok) throw new Error("download failed")
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement("a")
      link.href = url
      link.download = clip.alertId + ".mp4"
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 5_000)
    } catch { setDownloadError(true) }
    finally { setDownloadBusy(false) }
  }
  return <div className="flex h-full min-h-0 flex-col">
    <div className="border-b border-[var(--border-hairline)] px-3 py-3">
      <div className="flex items-center justify-between gap-2"><h2 className="flex items-center gap-2 text-xs font-semibold"><Film size={15} className="text-[var(--signal)]" />مقاطع مرتبطة</h2><button type="button" onClick={() => void fetchClips()} disabled={fixtureMode} aria-label="تحديث المقاطع" className="rounded p-1 text-[var(--text-tertiary)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40"><RefreshCw size={14} /></button></div>
      <p className="mt-1 text-[10px] text-[var(--text-tertiary)]">{selectedAlert ? "من الكاميرا أو الفئة نفسها ضمن التصفية" : "من التنبيهات الظاهرة ضمن التصفية"}</p>
    </div>
    <div className="min-h-0 flex-1 overflow-y-auto p-2">
      {fixtureMode ? <Empty title="لا توجد مقاطع للعينة" note="المعاينة التجريبية لا تحتوي أدلة مسجلة." />
        : status === "loading" ? <Empty title="جارٍ تحميل سجل المقاطع" note="التحقق من الملفات المحفوظة…" />
          : status === "error" ? <div className="space-y-3"><Empty title="تعذر جلب المقاطع" note={connectionStatus === "online" ? "تحقق من صلاحية الوصول إلى خدمة الأدلة." : "الخدمة غير متصلة حالياً أو يتعذر الوصول إليها."} /><button type="button" onClick={() => void fetchClips()} className="w-full rounded border border-[var(--border-hairline)] py-2 text-xs text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]">إعادة المحاولة</button></div>
            : related.length === 0 ? <Empty title="لا توجد مقاطع مرتبطة" note="قد لا يكون الدليل قد حُفظ بعد، أو لا يطابق التصفية الحالية." />
              : <div className="space-y-2">{related.map((clip) => {
                const alert = alertMap.get(clip.alertId)
                const type = alert?.type === "Weapon" || clip.type === "Weapon" || clip.type === "Weapon Detection" ? "رصد سلاح" : alert?.type === "Violence" || clip.type === "Violence" ? "رصد اعتداء" : "حادثة"
                return <button key={clip.alertId} type="button" onClick={() => { if (alert) onSelectAlert(alert); setModalClip(clip) }} className={"w-full rounded-md border p-2.5 text-start hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] " + (selectedAlertId === clip.alertId ? "border-[var(--signal)] bg-[var(--surface-2)]" : "border-[var(--border-hairline)]")}>
                  <span className="mb-2 flex aspect-video items-center justify-center rounded bg-[var(--surface-0)] text-[var(--text-tertiary)]"><Film size={20} /></span>
                  <strong className="block text-xs">{type}</strong>
                  <span className="mt-1 flex items-center gap-1 text-[10px] text-[var(--text-tertiary)]"><Camera size={11} /><InstrumentValue value={alert?.cameraId ?? clip.cameraId ?? "غير متوفر"} /></span>
                  <span className="mt-1 flex items-center gap-1 text-[10px] text-[var(--text-tertiary)]"><Clock3 size={11} /><InstrumentValue value={clipTime(clip, alert)} /><bdi className="instrument-num ms-auto">{formatSize(clip.size)}</bdi></span>
                </button>
              })}</div>}
    </div>
    {modalClip && <div ref={modalRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label="مراجعة مقطع الدليل" className="fixed inset-0 z-[120] grid place-items-center overflow-y-auto bg-[var(--surface-0)]/95 p-3 focus-visible:outline-none">
      <div className="w-full max-w-4xl rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-1)] p-3">
        <div className="mb-3 flex items-center justify-between"><div><strong className="text-sm">مقطع دليل مسجل</strong><bdi className="instrument-num ms-2 text-[10px] text-[var(--text-tertiary)]">{modalClip.alertId}</bdi></div><button type="button" autoFocus onClick={() => setModalClip(null)} aria-label="إغلاق المقطع" className="rounded p-1 text-[var(--text-secondary)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><X size={18} /></button></div>
        {privacyMode ? <div className="flex aspect-video min-h-[210px] flex-col items-center justify-center gap-2 rounded border border-[var(--border-hairline)] bg-[var(--surface-0)] px-5 text-center"><Film size={25} className="text-[var(--text-tertiary)]" /><strong className="text-sm">المقطع محجوب بوضع الخصوصية</strong><p className="text-xs text-[var(--text-tertiary)]">أوقف وضع الخصوصية لمراجعة الدليل المصور.</p></div>
          : <IncidentReplay alertId={modalClip.alertId} threatType={modalClip.type === "Weapon" || modalClip.type === "Weapon Detection" ? "weapon" : "violence"} confidence={modalClip.confidence ?? alertMap.get(modalClip.alertId)?.confidence ?? NaN} location={alertMap.get(modalClip.alertId)?.location ?? ""} timestamp={clipTime(modalClip, alertMap.get(modalClip.alertId))} autoPlay />}
        <div className="mt-3 flex items-center justify-between gap-2"><span className="text-[10px] text-[var(--text-tertiary)]">الملف مرتبط بالتنبيه المحدد، وليس بثاً حياً.</span><button type="button" disabled={downloadBusy || privacyMode} onClick={() => void download(modalClip)} className="inline-flex items-center gap-1 rounded border border-[var(--border-hairline)] px-3 py-2 text-xs text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40"><Download size={14} />{downloadBusy ? "جارٍ التنزيل…" : "حفظ المقطع"}</button></div>
        {downloadError && <p role="alert" className="mt-2 text-xs text-[var(--threat-critical)]">تعذر تنزيل المقطع. تحقق من الصلاحية أو الاتصال.</p>}
      </div>
    </div>}
  </div>
}

function Empty({ title, note }: { title: string; note: string }) {
  return <div className="flex min-h-[190px] flex-col items-center justify-center gap-2 px-3 text-center"><div className="grid size-11 place-items-center rounded-full border border-[var(--border-hairline)] text-[var(--text-tertiary)]"><Film size={20} /></div><strong className="text-xs text-[var(--text-primary)]">{title}</strong><p className="text-[10px] leading-5 text-[var(--text-tertiary)]">{note}</p></div>
}
