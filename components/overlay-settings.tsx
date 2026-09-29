"use client"

import { memo } from "react"
import { RotateCcw, Settings2, SlidersHorizontal } from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Slider } from "@/components/ui/slider"

export interface OverlaySettings {
  showBoxes: boolean
  showLabels: boolean
  showFps: boolean
  showPersonCount: boolean
  showTimestamp: boolean
  showThreatBadge: boolean
  opacity: number
  boxThickness: number
  labelStyle: "chip" | "plain"
}

const DEFAULT_SETTINGS: OverlaySettings = {
  showBoxes: true, showLabels: true, showFps: true, showPersonCount: true,
  showTimestamp: true, showThreatBadge: true, opacity: 85, boxThickness: 2, labelStyle: "chip",
}
const STORAGE_KEY = "ai-sentinel-overlay-settings"

function loadSettings(): OverlaySettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? { ...DEFAULT_SETTINGS, ...JSON.parse(raw) as Partial<OverlaySettings> } : DEFAULT_SETTINGS
  } catch { return DEFAULT_SETTINGS }
}

const TOGGLES: { key: keyof Pick<OverlaySettings, "showBoxes" | "showLabels" | "showFps" | "showPersonCount" | "showTimestamp" | "showThreatBadge">; label: string }[] = [
  { key: "showBoxes", label: "إطارات التحديد" }, { key: "showLabels", label: "تسميات الرصد" },
  { key: "showFps", label: "معدل الإطارات" }, { key: "showPersonCount", label: "عدد الأشخاص" },
  { key: "showTimestamp", label: "الوقت" }, { key: "showThreatBadge", label: "وسم التنبيه" },
]

export const OverlaySettingsPanel = memo(function OverlaySettingsPanel({ settings, onChange }: { settings: OverlaySettings; onChange: (settings: OverlaySettings) => void }) {
  const update = (patch: Partial<OverlaySettings>) => onChange({ ...settings, ...patch })
  return <Popover>
    <PopoverTrigger asChild><button type="button" className="inline-flex h-7 items-center gap-1.5 rounded border border-[var(--border-hairline)] bg-[var(--surface-1)] px-2.5 text-[10px] text-[var(--text-secondary)] hover:border-[var(--signal)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]" aria-label="إعدادات طبقة الرصد"><Settings2 size={13} />طبقة الرصد</button></PopoverTrigger>
    <PopoverContent align="start" sideOffset={8} className="w-[min(330px,calc(100vw-24px))] border-[var(--border-hairline)] bg-[var(--surface-2)] p-0 text-[var(--text-primary)] shadow-[var(--shadow-panel)] motion-reduce:!animate-none">
      <div className="flex items-center justify-between border-b border-[var(--border-hairline)] px-4 py-3"><span className="flex items-center gap-2 text-xs font-semibold"><SlidersHorizontal size={14} className="text-[var(--signal)]" />إعدادات طبقة الرصد</span><button type="button" onClick={() => onChange(DEFAULT_SETTINGS)} className="flex items-center gap-1 text-[10px] text-[var(--text-secondary)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><RotateCcw size={12} />افتراضي</button></div>
      <div className="space-y-4 p-4"><fieldset><legend className="mb-2 text-[10px] font-semibold text-[var(--text-tertiary)]">العناصر الظاهرة</legend><div className="grid grid-cols-2 gap-2">{TOGGLES.map(({ key, label }) => <label key={key} className="flex cursor-pointer items-center gap-2 rounded border border-[var(--border-hairline)] bg-[var(--surface-1)] px-2 py-2 text-[10px]"><input type="checkbox" checked={settings[key]} onChange={(event) => update({ [key]: event.target.checked })} className="size-3.5 accent-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]" />{label}</label>)}</div></fieldset>
        <div><div className="mb-2 flex items-center justify-between text-[10px]"><label id="overlay-opacity">شفافية الطبقة</label><bdi className="instrument-num text-[var(--signal)]" dir="ltr">{settings.opacity}%</bdi></div><Slider aria-labelledby="overlay-opacity" min={20} max={100} step={5} value={[settings.opacity]} onValueChange={([opacity]) => update({ opacity })} /></div>
        <div><div className="mb-2 flex items-center justify-between text-[10px]"><label id="overlay-thickness">سماكة الإطار</label><bdi className="instrument-num text-[var(--signal)]" dir="ltr">{settings.boxThickness} px</bdi></div><Slider aria-labelledby="overlay-thickness" min={1} max={6} step={1} value={[settings.boxThickness]} onValueChange={([boxThickness]) => update({ boxThickness })} /></div>
        <fieldset><legend className="mb-2 text-[10px]">شكل التسمية</legend><div className="flex gap-2">{(["chip", "plain"] as const).map((style) => <button key={style} type="button" aria-pressed={settings.labelStyle === style} onClick={() => update({ labelStyle: style })} className={`flex-1 rounded border px-2 py-1.5 text-[10px] focus-visible:outline-2 focus-visible:outline-[var(--signal)] ${settings.labelStyle === style ? "border-[var(--signal)] text-[var(--signal)]" : "border-[var(--border-hairline)] text-[var(--text-secondary)]"}`}>{style === "chip" ? "شارة" : "نص بسيط"}</button>)}</div></fieldset>
      </div>
    </PopoverContent>
  </Popover>
})

export { loadSettings, DEFAULT_SETTINGS }
