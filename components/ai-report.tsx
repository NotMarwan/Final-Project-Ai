"use client"

import { useState, useEffect, useRef } from "react"
import { FileSearch, Sparkles, Loader2, CheckCircle2, Info, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const VLM_TIMEOUT_MS  = 90_000   // 90 ثانية كحد أقصى للانتظار
const POLL_INTERVAL_MS = 2_000   // استعلام كل 2 ثانية

type VlmState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; report: string }
  | { status: "timeout" }
  | { status: "error"; message: string }

interface AiReportProps {
  alertId: string | undefined
}

export function AiReport({ alertId }: AiReportProps) {
  // خزّن التقارير لكل رصد حتى لا تضيع عند التبديل بين التنبيهات
  const reportCacheRef = useRef<Record<string, string>>({})
  const [vlmState, setVlmState] = useState<VlmState>({ status: "idle" })
  const pollTimerRef  = useRef<ReturnType<typeof setTimeout> | null>(null)
  const timeoutRef    = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isMountedRef  = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])

  // ── عند تغيير الحادث المحدد ── 
  useEffect(() => {
    // إلغاء أي polling سابق
    if (pollTimerRef.current !== null)  clearTimeout(pollTimerRef.current)
    if (timeoutRef.current !== null)    clearTimeout(timeoutRef.current)

    if (!alertId) {
      setVlmState({ status: "idle" })
      return
    }

    // إذا كان التقرير محفوظاً مسبقاً في الـ Cache، اعرضه فوراً
    if (reportCacheRef.current[alertId]) {
      setVlmState({ status: "ready", report: reportCacheRef.current[alertId] })
      return
    }

    // ابدأ تحميل جديد
    setVlmState({ status: "loading" })

    // ضبط مؤقت الـ Timeout الكلي
    timeoutRef.current = setTimeout(() => {
      if (!isMountedRef.current) return
      setVlmState((prev) =>
        prev.status === "loading" ? { status: "timeout" } : prev
      )
    }, VLM_TIMEOUT_MS)

    // دالة الاستعلام (Polling)
    const poll = async () => {
      if (!isMountedRef.current) return
      try {
        const res = await fetch(`${API_BASE}/get_report/${alertId}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()

        if (data.status === "ready" && data.report) {
          // Report ready
          if (timeoutRef.current !== null) clearTimeout(timeoutRef.current)
          reportCacheRef.current[alertId] = data.report
          if (isMountedRef.current) {
            setVlmState({ status: "ready", report: data.report })
          }
        } else {
          // Still generating, poll again
          pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch (err) {
        if (!isMountedRef.current) return
        const message = err instanceof Error ? err.message : "Unknown error"
        setVlmState({ status: "error", message })
        if (timeoutRef.current !== null) clearTimeout(timeoutRef.current)
      }
    }

    // ابدأ الاستعلام بعد ثانيتين (نعطي الـ backend وقتاً لبدء التوليد)
    pollTimerRef.current = setTimeout(poll, 2_000)

    return () => {
      if (pollTimerRef.current !== null) clearTimeout(pollTimerRef.current)
      if (timeoutRef.current !== null)   clearTimeout(timeoutRef.current)
    }
  }, [alertId])

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden flex flex-col h-full shadow-inner">
      {/* هيدر */}
      <div className="flex flex-shrink-0 items-center gap-2 border-b border-border px-4 py-2.5 bg-muted/20">
        <FileSearch className="h-3.5 w-3.5 text-primary" />
        <span className="text-xs font-semibold text-foreground">AI Forensic Analysis Report</span>
        <div className="ml-auto flex items-center gap-1.5 border border-primary/20 bg-primary/5 px-2 py-0.5 rounded-md">
          <Sparkles className="h-3 w-3 text-primary animate-pulse" />
          <span className="font-mono text-[9px] text-primary uppercase tracking-wider font-bold">
            Groq Vision AI
          </span>
        </div>
      </div>

      {/* المحتوى */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-4">

        {/* حالة التحميل */}
        {vlmState.status === "loading" && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center py-4">
            <div className="relative flex h-10 w-10 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/20" />
              <Loader2 className="relative h-5 w-5 text-primary animate-spin" />
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">Generating Forensic Report...</p>
              <p className="mt-1 text-[10px] text-muted-foreground leading-relaxed">
                Groq AI is analyzing the incident frame and writing a detailed security report. <br />
                Estimated time: 3–7 seconds.
              </p>
            </div>
          </div>
        )}

        {/* حالة الجاهزية */}
        {vlmState.status === "ready" && (
          <div className="space-y-3">
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3.5">
              <p
                className="text-[14px] leading-loose text-foreground whitespace-pre-wrap font-medium"
              >
                {vlmState.report}
              </p>
            </div>
            <p className="flex items-center gap-1.5 text-[9px] text-muted-foreground font-medium pt-1 border-t border-border/50">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              Automated forensic report generated by Groq AI based on camera frames.
            </p>
          </div>
        )}

        {/* حالة انتهاء المهلة */}
        {vlmState.status === "timeout" && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center p-4 border border-border bg-secondary/30 rounded-lg">
            <Info className="h-8 w-8 text-muted-foreground/60" />
            <p className="text-xs leading-relaxed text-muted-foreground font-medium">
              Report generation took longer than usual. <br />
              Please check your connection and Groq API key.
            </p>
          </div>
        )}

          <div className="flex items-start gap-2.5 rounded-lg border border-red-500/20 bg-red-500/5 p-3.5 shadow-inner">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-400" />
            <p className="text-[11px] leading-relaxed text-red-400/90 font-medium">
              Report failed: {vlmState.message}
            </p>
          </div>

          <div className="flex h-full flex-col items-center justify-center gap-2 py-6 text-center text-muted-foreground/50 border border-dashed border-border/70 rounded-lg">
            <FileSearch className="h-8 w-8 opacity-40" />
            <p className="text-xs font-medium">Select an incident from the feed to view report.</p>
          </div>
      </div>
    </div>
  )
}