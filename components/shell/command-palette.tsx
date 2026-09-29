"use client"

import { useEffect, useState } from "react"
import { Eye, EyeOff, Search, ShieldAlert, X } from "lucide-react"
import type { LiveAlert } from "@/components/video-player"
import { SECTIONS, type Section } from "./app-shell"

export function CommandPalette({ open, onClose, onNavigate, alerts, onSelectAlert, privacyMode, onTogglePrivacy }: {
  open: boolean
  onClose: () => void
  onNavigate: (section: Section) => void
  alerts: LiveAlert[]
  onSelectAlert: (alert: LiveAlert) => void
  privacyMode: boolean
  onTogglePrivacy: () => void
}) {
  const [query, setQuery] = useState("")
  useEffect(() => { if (open) setQuery("") }, [open])
  useEffect(() => {
    if (!open) return
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose() }
    window.addEventListener("keydown", close)
    return () => window.removeEventListener("keydown", close)
  }, [open, onClose])
  if (!open) return null
  const choices = SECTIONS.filter((section) => section.label.includes(query) || String(SECTIONS.indexOf(section) + 1) === query)
  const alertChoices = query.trim() ? alerts.filter((alert) => `${alert.id} ${alert.cameraId} ${alert.location}`.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 5) : []
  return <div className="palette-backdrop" onMouseDown={onClose} role="presentation"><div className="command-palette" role="dialog" aria-modal="true" aria-label="لوحة الأوامر" onMouseDown={(event) => event.stopPropagation()}>
    <div className="palette-input"><Search size={18} /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ابحث عن محطة عمل…" aria-label="البحث في المحطات" /><button onClick={onClose} aria-label="إغلاق"><X size={17} /></button></div>
    <div className="palette-caption">الانتقال إلى</div>
    {choices.map(({ id, label, icon: Icon }, index) => <button key={id} className="palette-result" onClick={() => { onNavigate(id); onClose() }}><Icon size={17} />{label}<kbd className="instrument-num">{index + 1}</kbd></button>)}
    {alertChoices.length > 0 && <><div className="palette-caption">حوادث مستلمة</div>{alertChoices.map((alert) => <button key={alert.id} className="palette-result" onClick={() => { onSelectAlert(alert); onClose() }}><ShieldAlert size={17} /><bdi className="instrument-num">{alert.cameraId}</bdi>{alert.location}<small>{alert.type === "Weapon" ? "سلاح" : "اعتداء"}</small></button>)}</>}
    {!query.trim() && <><div className="palette-caption">إجراء سريع</div><button className="palette-result" onClick={() => { onTogglePrivacy(); onClose() }}>{privacyMode ? <EyeOff size={17} /> : <Eye size={17} />}{privacyMode ? "إيقاف وضع الخصوصية" : "تفعيل وضع الخصوصية"}</button></>}
    {choices.length === 0 && alertChoices.length === 0 && <p className="palette-empty">لا توجد نتائج</p>}
  </div></div>
}
