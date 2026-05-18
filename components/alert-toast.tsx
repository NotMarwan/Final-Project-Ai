"use client"

import { useEffect, useState, useCallback } from "react"
import { ShieldAlert, X, ArrowRight } from "lucide-react"
import { isToastSuppressedForTab } from "@/lib/live-visual-state"
import { cn } from "@/lib/utils"
import type { LiveAlert } from "@/components/video-player"

interface AlertToastProps {
  alert: LiveAlert | null
  activeTab: string
  onNavigate: () => void
  onDismiss: () => void
}

export function AlertToast({ alert, activeTab, onNavigate, onDismiss }: AlertToastProps) {
  const [visible, setVisible] = useState(false)
  const [dismissing, setDismissing] = useState(false)

  const handleDismiss = useCallback(() => {
    setDismissing(true)
    setTimeout(() => {
      setVisible(false)
      onDismiss()
    }, 300)
  }, [onDismiss])

  useEffect(() => {
    if (isToastSuppressedForTab(activeTab)) {
      if (alert || visible || dismissing) {
        setVisible(false)
        setDismissing(false)
        if (alert) {
          onDismiss()
        }
      }
      return
    }
    if (!alert) return
    setDismissing(false)
    setVisible(true)
    const id = setTimeout(() => {
      handleDismiss()
    }, 6000)
    return () => clearTimeout(id)
  }, [activeTab, alert, dismissing, handleDismiss, onDismiss, visible])

  const handleNavigate = useCallback(() => {
    setDismissing(true)
    setTimeout(() => {
      setVisible(false)
      onNavigate()
    }, 200)
  }, [onNavigate])

  if (!visible || !alert) return null

  const isCritical = alert.severity === "critical"

  return (
    <div
      className={cn(
        "fixed top-4 right-4 z-[90] w-[340px] max-w-[calc(100vw-2rem)]",
        "transform transition-all duration-300 ease-out",
        dismissing ? "translate-x-full opacity-0" : "translate-x-0 opacity-100"
      )}
    >
      <div
        className={cn(
          "rounded-xl border p-3 shadow-2xl backdrop-blur-xl",
          isCritical
            ? "bg-danger/10 border-danger/40 shadow-danger/10"
            : "bg-warning/10 border-warning/40 shadow-warning/10"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <div className="relative">
              <span className={cn("absolute inset-0 rounded-full blur-md animate-ambient-pulse", isCritical ? "bg-danger/40" : "bg-warning/40")} />
              <ShieldAlert className={cn("h-4 w-4 relative z-10", isCritical ? "text-danger" : "text-warning")} />
            </div>
            <span className={cn("text-sm font-bold uppercase tracking-wider", isCritical ? "text-danger" : "text-warning")}>
              {alert.severity} Alert
            </span>
          </div>
          <button
            onClick={handleDismiss}
            className="rounded-md p-2 min-h-[44px] min-w-[44px] flex items-center justify-center text-muted-foreground/50 hover:text-foreground hover:bg-white/5 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex items-center gap-2 mb-1">
          <p className="text-base font-semibold text-foreground">
            {alert.type} detected on {alert.cameraId}
          </p>
          <span className={`rounded px-2 py-0.5 text-xs font-bold border ${
            alert.cameraId.startsWith("EXAMPLE-")
              ? "bg-amber-500/20 text-amber-400 border-amber-500/30"
              : "bg-red-500/20 text-red-400 border-red-500/30"
          }`}>
            {alert.cameraId.startsWith("EXAMPLE-") ? "DEMO" : "LIVE"}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          Confidence: {Math.round(alert.confidence)}% • {alert.location}
        </p>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleNavigate}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 rounded-lg px-3 py-2.5 min-h-[44px] text-[11px] font-semibold transition-colors",
              isCritical
                ? "bg-danger text-white hover:bg-danger/90"
                : "bg-warning text-black hover:bg-warning/90"
            )}
          >
            <span>View Incident</span>
            <ArrowRight className="h-3 w-3" />
          </button>
          <button
            onClick={handleDismiss}
            className="px-3 py-2.5 min-h-[44px] text-[11px] text-muted-foreground hover:text-foreground transition-colors"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  )
}
