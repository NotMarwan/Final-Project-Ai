"use client"

import { memo } from "react"
import { cn } from "@/lib/utils"

interface ConfidenceBar {
  label: string
  value: number
  color: string
  icon?: string
}

interface ConfidenceBarsProps {
  bars: ConfidenceBar[]
  visible: boolean
}

export const ConfidenceBars = memo(function ConfidenceBars({ bars, visible }: ConfidenceBarsProps) {
  if (!visible || !bars.length) return null

  return (
    <div className="pointer-events-none absolute bottom-16 left-3 right-3 z-20">
      <div className="backdrop-blur-sm bg-black/70 rounded-lg border border-white/10 px-3 py-2 space-y-1.5">
        {bars.map((bar) => (
          <div key={bar.label} className="flex items-center gap-2">
            {bar.icon && (
              <span className="text-xs leading-none">{bar.icon}</span>
            )}
            <span className="font-mono text-[10px] text-white/80 w-16 truncate">{bar.label}</span>
            <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
              <div
                className={cn("h-full rounded-full transition-all duration-500", bar.color)}
                style={{ width: `${Math.min(100, Math.max(0, bar.value))}%` }}
              />
            </div>
            <span className="font-mono text-[10px] text-white/60 w-8 text-right">
              {bar.value.toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
})