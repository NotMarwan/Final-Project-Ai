"use client"

import { memo, useState, useEffect, useCallback } from "react"
import {
  Settings2, Layers, Tag, Gauge, Users,
  SlidersHorizontal, Eye, EyeOff, RotateCcw,
  Palette, Minus, Plus
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { cn } from "@/lib/utils"

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
  showBoxes: true,
  showLabels: true,
  showFps: true,
  showPersonCount: true,
  showTimestamp: true,
  showThreatBadge: true,
  opacity: 85,
  boxThickness: 2,
  labelStyle: "chip",
}

const STORAGE_KEY = "ai-sentinel-overlay-settings"

function loadSettings(): OverlaySettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_SETTINGS
    const parsed = JSON.parse(raw) as Partial<OverlaySettings>
    return { ...DEFAULT_SETTINGS, ...parsed }
  } catch {
    return DEFAULT_SETTINGS
  }
}

interface OverlaySettingsPanelProps {
  settings: OverlaySettings
  onChange: (s: OverlaySettings) => void
}

export const OverlaySettingsPanel = memo(function OverlaySettingsPanel({
  settings,
  onChange,
}: OverlaySettingsPanelProps) {
  const [open, setOpen] = useState(false)

  const update = useCallback(
    (patch: Partial<OverlaySettings>) => onChange({ ...settings, ...patch }),
    [settings, onChange]
  )

  const reset = useCallback(() => onChange(DEFAULT_SETTINGS), [onChange])

  return (
    <div className="relative">
      <Button
        variant={open ? "default" : "ghost"}
        size="sm"
        className={cn(
          "h-8 gap-1.5 text-xs transition-all",
          open ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
        )}
        onClick={() => setOpen((v) => !v)}
      >
        <Settings2 className="h-3.5 w-3.5" />
        Overlay
      </Button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-full mt-2 z-50 w-72 rounded-xl border border-border bg-card shadow-xl animate-scale-in">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">Overlay Settings</span>
              </div>
              <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={reset} title="Reset defaults">
                <RotateCcw className="h-3 w-3" />
              </Button>
            </div>

            <div className="p-4 space-y-5">
              {/* Toggle Row */}
              <div className="space-y-3">
                <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                  <Eye className="h-3 w-3" /> Visibility
                </p>
                {[
                  { key: "showBoxes" as const, label: "Bounding Boxes", icon: Layers },
                  { key: "showLabels" as const, label: "Labels", icon: Tag },
                  { key: "showPersonCount" as const, label: "Person Count", icon: Users },
                  { key: "showFps" as const, label: "FPS Counter", icon: Gauge },
                  { key: "showTimestamp" as const, label: "Timestamp", icon: Eye },
                  { key: "showThreatBadge" as const, label: "Threat Badge", icon: Palette },
                ].map(({ key, label, icon: Icon }) => (
                  <div key={key} className="flex items-center justify-between">
                    <span className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Icon className="h-3 w-3" />
                      {label}
                    </span>
                    <button
                      onClick={() => update({ [key]: !settings[key] })}
                      className={cn(
                        "relative h-6 w-11 rounded-full transition-colors duration-200",
                        settings[key] ? "bg-primary" : "bg-muted"
                      )}
                    >
                      <span
                        className={cn(
                          "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-200",
                          settings[key] ? "translate-x-5" : "translate-x-0.5"
                        )}
                      />
                    </button>
                  </div>
                ))}
              </div>

              {/* Opacity Slider */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                    <SlidersHorizontal className="h-3 w-3" /> Opacity
                  </p>
                  <span className="font-mono text-xs text-primary">{settings.opacity}%</span>
                </div>
                <Slider
                  value={[settings.opacity]}
                  min={20}
                  max={100}
                  step={5}
                  onValueChange={([v]) => update({ opacity: v })}
                  className="w-full"
                />
              </div>

              {/* Box Thickness Slider */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                    <Minus className="h-3 w-3" /> Box Thickness
                  </p>
                  <span className="font-mono text-xs text-primary">{settings.boxThickness}px</span>
                </div>
                <Slider
                  value={[settings.boxThickness]}
                  min={1}
                  max={6}
                  step={1}
                  onValueChange={([v]) => update({ boxThickness: v })}
                  className="w-full"
                />
              </div>

              {/* Label Style */}
              <div className="space-y-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                  <Tag className="h-3 w-3" /> Label Style
                </p>
                <div className="flex gap-2">
                  {(["chip", "plain"] as const).map((style) => (
                    <button
                      key={style}
                      onClick={() => update({ labelStyle: style })}
                      className={cn(
                        "flex-1 rounded-lg border py-1.5 text-xs font-medium transition-colors",
                        settings.labelStyle === style
                          ? "border-primary bg-primary/10 text-primary"
                          : "border-border text-muted-foreground hover:border-primary/50"
                      )}
                    >
                      {style === "chip" ? "Chip" : "Plain"}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
})

export { loadSettings, DEFAULT_SETTINGS }