"use client"

import { useCallback, useEffect, useState } from "react"
import { Bell, RefreshCw, Send } from "lucide-react"
import { apiFetch } from "@/lib/api-auth"
import { formatDateTime24 } from "@/components/shell/locale"
import { useSentinel } from "@/lib/sentinel-store"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const ACTION = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-[var(--border-hairline)] px-3 text-xs text-[var(--text-secondary)] hover:border-[var(--signal)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-50"

interface TelegramStatus {
  enabled: boolean
  ready?: boolean
  configured?: boolean
  lastSendStatus?: string | null
  lastError?: string | null
  lastSentAt?: string | null
  minAlertIntervalSeconds?: number
  provider?: string
  running: boolean
  min_severity?: string
}

interface TelegramStatusCardProps {
  status?: TelegramStatus
  isAdmin?: boolean
}

export function TelegramStatusCard({ status: propStatus, isAdmin = false }: TelegramStatusCardProps) {
  const { connectionStatus, fixtureMode } = useSentinel()
  const offline = !propStatus && (fixtureMode || connectionStatus !== "online")
  const [status, setStatus] = useState<TelegramStatus | null>(propStatus ?? null)
  const [loading, setLoading] = useState(!propStatus && !offline)
  const [unavailable, setUnavailable] = useState(offline)
  const [testLoading, setTestLoading] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const response = await apiFetch(`${API_BASE}/system/status`)
      if (!response.ok) throw new Error("status unavailable")
      const data: unknown = await response.json()
      if (!data || typeof data !== "object" || !("notifications" in data) || !data.notifications || typeof data.notifications !== "object") throw new Error("status missing")
      const notifications = data.notifications as Record<string, unknown>
      if (typeof notifications.enabled !== "boolean" || typeof notifications.running !== "boolean") throw new Error("invalid status")
      setStatus(notifications as unknown as TelegramStatus)
      setUnavailable(false)
    } catch {
      setStatus(null)
      setUnavailable(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (propStatus) { setStatus(propStatus); setLoading(false); setUnavailable(false); return }
    if (offline) return
    void fetchStatus()
    const interval = window.setInterval(fetchStatus, 30_000)
    return () => window.clearInterval(interval)
  }, [propStatus, fetchStatus, offline])

  const handleTest = async () => {
    setTestLoading(true)
    setTestResult(null)
    try {
      const response = await apiFetch(`${API_BASE}/notifications/telegram/test`, { method: "POST" })
      const data: { success?: boolean } = await response.json().catch(() => ({}))
      setTestResult(response.ok && data.success ? "تم إرسال رسالة الاختبار." : "تعذر إرسال رسالة الاختبار. راجع إعدادات القناة وصلاحيات الجلسة.")
      if (response.ok && data.success) window.setTimeout(fetchStatus, 1000)
    } catch {
      setTestResult("تعذر الوصول إلى الخادم لإرسال رسالة الاختبار.")
    } finally {
      setTestLoading(false)
    }
  }

  const ready = status?.ready ?? (status?.configured === true && status?.enabled === true)
  const label = offline ? "غير متاح" : loading ? "جارٍ التحقق" : unavailable || !status ? "غير متاح" : !status.enabled ? "معطّلة" : !ready ? "غير جاهزة" : status.running ? "تعمل" : "متوقفة"
  const tone = offline || unavailable || !status ? "var(--state-offline)" : status.enabled && ready && status.running ? "var(--signal)" : "var(--threat-high)"
  return <section className="overflow-hidden rounded-[var(--radius-panel)] border border-[var(--border-hairline)] bg-[var(--surface-1)]" aria-label="حالة قناة تيليجرام">
    <div className="flex items-start justify-between gap-2 border-b border-[var(--border-hairline)] p-4"><div className="flex items-center gap-3"><Bell size={18} className="text-[var(--signal)]" /><div><h2 className="text-sm font-semibold">قناة الإشعارات</h2><p className="mt-1 text-[10px] text-[var(--text-tertiary)]">تكامل <bdi dir="ltr">Telegram</bdi></p></div></div><span role="status" className="rounded border px-2 py-1 text-[11px]" style={{ color: tone, borderColor: tone }}>{label}</span></div>
    <div className="space-y-3 p-4"><p className="text-[11px] leading-5 text-[var(--text-secondary)]">المصدر: <bdi dir="ltr" className="instrument-num">GET /system/status · notifications</bdi></p>
      {status && !unavailable && !offline ? <dl className="space-y-2 border-t border-[var(--border-hairline)] pt-3 text-xs"><div className="flex justify-between gap-3"><dt className="text-[var(--text-tertiary)]">التمكين</dt><dd>{status.enabled ? "مفعّلة" : "معطّلة"}</dd></div><div className="flex justify-between gap-3"><dt className="text-[var(--text-tertiary)]">جاهزية الإرسال</dt><dd>{ready ? "جاهزة حسب الخادم" : "غير جاهزة"}</dd></div><div className="flex justify-between gap-3"><dt className="text-[var(--text-tertiary)]">آخر إرسال</dt><dd>{status.lastSendStatus === "success" ? "ناجح" : status.lastSendStatus === "failed" ? "فشل" : status.lastSendStatus === "cooldown" ? "في فترة التهدئة" : "غير متاح"}</dd></div><div className="flex justify-between gap-3"><dt className="text-[var(--text-tertiary)]">وقت آخر إرسال</dt><dd>{typeof status.lastSentAt === "string" && !Number.isNaN(Date.parse(status.lastSentAt)) ? formatDateTime24(status.lastSentAt) : "غير متاح"}</dd></div></dl> : <p className="rounded border border-[var(--border-hairline)] bg-[var(--surface-2)] p-3 text-xs leading-5 text-[var(--text-secondary)]">{offline ? "قناة التنبيهات غير متصلة؛ حالة التكامل غير مؤكدة." : loading ? "جارٍ تحميل حالة التكامل…" : "تعذر الحصول على حالة قناة الإشعارات من الخادم."}</p>}
      {status?.lastError && !unavailable && <p className="text-xs text-[var(--threat-high)]">أبلغ الخادم عن خطأ في آخر محاولة إرسال. راجع سجلات الخادم.</p>}
      {testResult && <p role="status" className="text-xs text-[var(--text-secondary)]">{testResult}</p>}
      <div className="flex flex-wrap gap-2 pt-1"><button className={ACTION} onClick={() => void fetchStatus()}><RefreshCw size={13} />تحديث الحالة</button>{isAdmin && ready && <button className={ACTION} onClick={() => void handleTest()} disabled={testLoading}><Send size={13} />{testLoading ? "جارٍ الإرسال…" : "إرسال رسالة اختبار"}</button>}</div>
    </div>
  </section>
}
