"use client"

import { memo } from "react"

type ConfidenceBar = { label: string; value: number; color: string; icon?: string }

export const ConfidenceBars = memo(function ConfidenceBars({ bars, visible }: { bars: ConfidenceBar[]; visible: boolean }) {
  if (!visible || bars.length === 0) return null
  return <div className="pointer-events-none absolute bottom-12 end-3 z-20 w-[min(260px,calc(100%-24px))] rounded-md border border-[var(--border-hairline)] bg-[var(--surface-1)]/90 p-2.5 shadow-[var(--shadow-panel)] backdrop-blur-md" aria-label="درجات الرصد الحالية">
    <div className="mb-2 text-[10px] font-semibold text-[var(--text-secondary)]">درجات النماذج</div>
    <div className="space-y-2">{bars.map((bar) => <div key={bar.label} className="grid grid-cols-[50px_1fr_34px] items-center gap-2 text-[10px]"><span className="truncate" style={{ color: bar.color }}>{bar.label}</span><span className="h-1 overflow-hidden rounded-full bg-[var(--surface-3)]"><span className="block h-full rounded-full " style={{ width: `${Math.max(0, Math.min(100, bar.value))}%`, backgroundColor: bar.color }} /></span><bdi className="instrument-num text-end text-[var(--text-secondary)]" dir="ltr">{Number.isFinite(bar.value) ? Math.round(bar.value) : 0}%</bdi></div>)}</div>
  </div>
})
