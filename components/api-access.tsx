"use client"

import { type FormEvent, useState } from "react"
import { KeyRound, LockKeyhole, ShieldCheck, X } from "lucide-react"
import { apiFetch, clearApiCredential, saveApiCredential } from "@/lib/api-auth"
import { useApiAccess } from "@/hooks/use-api-access"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const ACTION = "inline-flex min-h-9 items-center justify-center gap-2 rounded-md border border-[var(--border-hairline)] px-3 text-xs text-[var(--text-secondary)] hover:border-[var(--signal)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-50"

export function ApiAccess() {
  const { state: accessState, setState, role, expired } = useApiAccess()
  const [credential, setCredential] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)

  const connect = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError("")
    try {
      saveApiCredential(credential)
      const response = await apiFetch(`${API_BASE}/security/session`)
      if (!response.ok) {
        clearApiCredential()
        setError(response.status === 401 ? "مفتاح واجهة البرمجة غير صحيح." : "تعذر التحقق من الجلسة.")
        return
      }
      setCredential("")
      setState("verified")
      window.location.reload()
    } catch {
      clearApiCredential()
      setError("تعذر التحقق من الجلسة.")
    } finally {
      setBusy(false)
    }
  }
  const disconnect = () => { clearApiCredential(); window.location.reload() }
  const shownError = error || (expired ? "انتهت صلاحية مفتاح الجلسة المحفوظ." : "")

  return <div className="p-4 text-xs">
    {accessState === "checking" && <p role="status" className="text-[var(--text-secondary)]">جارٍ التحقق من وصول الجلسة…</p>}
    {accessState === "offline" && <p role="status" className="rounded border border-[var(--border-hairline)] bg-[var(--surface-2)] p-3 text-[var(--state-offline)]">حالة المصادقة غير متاحة لأن الخادم لا يستجيب.</p>}
    {accessState === "unconfigured" && <p role="status" className="rounded border border-[var(--threat-high)] bg-[var(--surface-2)] p-3 text-[var(--threat-high)]">وصول القراءة مفتوح بحسب الخادم. إجراءات المشغّل معطّلة حتى إعداد مفتاح الإدارة.</p>}
    {accessState === "verified" && <div className="flex flex-wrap items-center justify-between gap-3"><span className="inline-flex items-center gap-2 text-[var(--signal)]"><ShieldCheck size={16} />جلسة محلية موثّقة <span className="text-[var(--text-secondary)]">· {role === "admin" ? "مشغّل" : role === "viewer" ? "قارئ" : "الدور غير متاح"}</span></span><button className={ACTION} onClick={disconnect}><X size={14} />مسح مفتاح الجلسة</button></div>}
    {accessState === "required" && <form onSubmit={connect} className="space-y-3"><label htmlFor="sentinel-api-key" className="flex items-center gap-2 font-medium"><LockKeyhole size={15} className="text-[var(--threat-high)]" />مفتاح واجهة البرمجة للمشغّل</label><div className="flex flex-wrap gap-2"><div className="relative min-w-44 flex-1"><KeyRound size={15} className="pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]" /><input id="sentinel-api-key" type="password" autoComplete="off" value={credential} onChange={event => setCredential(event.target.value)} className="h-9 w-full rounded-md border border-[var(--border-hairline)] bg-[var(--surface-0)] ps-9 pe-3 text-sm outline-none focus-visible:border-[var(--signal)]" placeholder="أدخل مفتاح الخادم المحلي" /></div><button type="submit" className={ACTION} disabled={busy || !credential.trim()}>{busy ? "جارٍ التحقق…" : "اتصال"}</button></div>{shownError && <p role="alert" className="text-[var(--threat-critical)]">{shownError}</p>}</form>}
    <p className="mt-3 text-[10px] leading-5 text-[var(--text-tertiary)]">المصدر: <bdi dir="ltr" className="instrument-num">/security/status · /security/session</bdi>. يُحفظ المفتاح في هذه الجلسة من المتصفح فقط.</p>
  </div>
}
