"use client"

import { useState, useEffect, useRef } from "react"
import { FileSearch, Sparkles, Loader2, CheckCircle2, Info, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const VLM_TIMEOUT_MS = 45_000

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
  const [vlmState, setVlmState] = useState<VlmState>({ status: "idle" })
  const vlmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── الاستماع لحدث استقبال التقرير عبر SSE ──
  useEffect(() => {
    const es = new EventSource(`${API_BASE}/alerts`)

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // التأكد أن الحدث هو تقرير وأن المعرف يطابق الحادث المحدد حالياً
        if (data.type !== "VLM_Report" || data.id !== alertId) return
        
        setVlmState({ status: "ready", report: data.report })
        
        // إلغاء مؤقت المهلة (Timeout) عند وصول التقرير
        if (vlmTimerRef.current !== null) clearTimeout(vlmTimerRef.current)
      } catch { }
    }

    es.onerror = () => { }

    return () => es.close()
  }, [alertId])

  // ── إدارة حالة التحميل والمهلة عند تغيير الحادث المحدد ──
  useEffect(() => {
    if (!alertId) {
      setVlmState({ status: "idle" })
      return
    }

    // تعيين حالة التحميل وبدء المؤقت
    setVlmState({ status: "loading" })

    if (vlmTimerRef.current !== null) clearTimeout(vlmTimerRef.current)
    vlmTimerRef.current = setTimeout(() => {
      setVlmState((prev) =>
        prev.status === "loading" ? { status: "timeout" } : prev
      )
    }, VLM_TIMEOUT_MS)

    return () => {
      if (vlmTimerRef.current !== null) clearTimeout(vlmTimerRef.current)
    }
  }, [alertId])

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden flex flex-col h-full shadow-inner">
      {/* هيدر ثابت */}
      <div className="flex flex-shrink-0 items-center gap-2 border-b border-border px-4 py-2.5 bg-muted/20">
        <FileSearch className="h-3.5 w-3.5 text-primary" />
        <span className="text-xs font-semibold text-foreground">AI Forensic Analysis Report</span>
        <div className="ml-auto flex items-center gap-1.5 border border-primary/20 bg-primary/5 px-2 py-0.5 rounded-md">
          <Sparkles className="h-3 w-3 text-primary animate-pulse" />
          <span className="font-mono text-[9px] text-primary uppercase tracking-wider font-bold">
            Groq LPU
          </span>
        </div>
      </div>

      {/* منطقة المحتوى: تشغل باقي المساحة العمودية وتسمح بالسحاب (overflow-y-auto) */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-4">
        {vlmState.status === "loading" && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center py-4">
            <div className="relative flex h-10 w-10 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/20" />
              <Loader2 className="relative h-5 w-5 text-primary animate-spin" />
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">Generating detailed report...</p>
              <p className="mt-1 text-[10px] text-muted-foreground leading-relaxed">
                Analyzing visual evidence via LLaMA 3.2 Vision on Groq hardware. <br/> Estimated time: ~10 seconds.
              </p>
            </div>
          </div>
        )}

        {vlmState.status === "ready" && (
          <div className="space-y-3">
            {/* منطقة النص: واسعة لعرض الكلام بالكامل، مع تنسيق يسمح بالتفاف النص (whitespace-pre-wrap) */}
            <div className="rounded-lg border border-primary/20 bg-primary/5 p-3.5">
<p className="text-[14px] leading-loose text-foreground whitespace-pre-wrap font-bold text-right" dir="rtl">                {vlmState.report}
              </p>
            </div>
            <p className="flex items-center gap-1.5 text-[9px] text-muted-foreground font-medium pt-1 border-t border-border/50">
              <CheckCircle2 className="h-3.5 w-3.5 text-success" />
              This is an automatically generated forensic description based on camera frames.
            </p>
          </div>
        )}

        {vlmState.status === "timeout" && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center p-4 border border-border bg-secondary/30 rounded-lg">
            <Info className="h-8 w-8 text-muted-foreground/60" />
            <p className="text-xs leading-relaxed text-muted-foreground font-medium">
              Report generation is taking longer than usual (Timeout). <br/>
              Check Python server logs or network connection to Groq API.
            </p>
          </div>
        )}

        {vlmState.status === "error" && (
          <div className="flex items-start gap-2.5 rounded-lg border border-danger/20 bg-danger/5 p-3.5 shadow-inner shadow-danger/5">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-danger" />
            <p className="text-[11px] leading-relaxed text-danger/90 font-medium">
              Report Error: {vlmState.message}
            </p>
          </div>
        )}

        {vlmState.status === "idle" && (
          <div className="flex h-full flex-col items-center justify-center gap-2 py-6 text-center text-muted-foreground/50 border border-dashed border-border/70 rounded-lg">
            <FileSearch className="h-8 w-8 opacity-40" />
            <p className="text-xs font-medium">Select an incident to view report.</p>
          </div>
        )}
      </div>
    </div>
  )
}
