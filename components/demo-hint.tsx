"use client"

import { useState, useEffect } from "react"
import { ChevronDown, ChevronUp, Info } from "lucide-react"
import { cn } from "@/lib/utils"

const STORAGE_KEY = "sentinel_demo_hint_dismissed"

export function DemoHint() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    setOpen(stored !== "true")
  }, [])

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (!next) localStorage.setItem(STORAGE_KEY, "true")
  }

  return (
    <div className="mx-4 mt-2 rounded-lg border border-border bg-card/60 overflow-hidden">
      <button
        onClick={toggle}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <Info className="h-3.5 w-3.5 text-primary" />
        <span>How to demo</span>
        {open ? <ChevronUp className="h-3.5 w-3.5 ml-auto" /> : <ChevronDown className="h-3.5 w-3.5 ml-auto" />}
      </button>
      {open && (
        <div className="px-4 pb-3 pt-1 border-t border-border space-y-1.5">
          <Step n={1} text='Select CAM-01 in the Live Monitor tab' />
          <Step n={2} text='Click the "Demo Clips" tab → choose a scenario' />
          <Step n={3} text='Hold a fake gun or knife clearly in front of the camera — watch the AI detect it in real time' />
        </div>
      )}
    </div>
  )
}

function Step({ n, text }: { n: number; text: string }) {
  return (
    <div className="flex items-start gap-2 text-xs text-muted-foreground">
      <span className={cn(
        "h-4 w-4 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-[10px] flex-shrink-0 mt-px"
      )}>
        {n}
      </span>
      <span>{text}</span>
    </div>
  )
}
