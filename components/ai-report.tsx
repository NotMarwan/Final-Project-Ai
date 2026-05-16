"use client"

import { useState, useEffect, useCallback } from "react"
import {
  FileSearch,
  Sparkles,
  Loader2,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Copy,
  ClipboardCheck,
} from "lucide-react"
import { cn } from "@/lib/utils"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
// No hardcoded key fallback — backend runs in open demo mode when no API key is configured.
const API_KEY = process.env.NEXT_PUBLIC_ADMIN_API_KEY
const authHeaders: Record<string, string> = API_KEY ? { "X-API-Key": API_KEY } : {}

interface ReportData {
  // v2 fields
  executive_summary?: string
  incident_classification?: string
  source_and_evidence?: string
  confidence_analysis?: string
  timeline?: string | string[]
  behavioral_interpretation?: string
  risk_assessment?: string
  operator_actions?: string | string[]
  demo_explanation?: string
  limitations?: string | string[]
  final_verdict?: string
  // v1 backward compat
  incident_type?: string
  severity_assessment?: string
  confidence_interpretation?: string
  camera_source?: string
  observed_evidence?: string
  recommended_actions?: string | string[]
  demo_notes_for_graduation_committee?: string
  raw?: boolean
}

interface ReportEnvelope {
  alert_id: string
  generated_at: string
  model: string
  report: ReportData
}

type State =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "no_report" }
  | { status: "generating" }
  | { status: "ready"; data: ReportEnvelope }
  | { status: "error"; message: string }

interface AiReportProps {
  alertId: string | undefined
}

function toLines(value: string | string[] | undefined): string[] {
  if (!value) return []
  if (Array.isArray(value)) return value.map(String).filter(Boolean)
  return [String(value)]
}

function Section({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1">
      <p className="text-[10px] font-bold uppercase tracking-widest text-primary/70">
        {label}
      </p>
      <div className="text-[12px] leading-relaxed text-foreground">{children}</div>
    </div>
  )
}

export function AiReport({ alertId }: AiReportProps) {
  const [state, setState] = useState<State>({ status: "idle" })
  const [copied, setCopied] = useState(false)
  const [missingKey, setMissingKey] = useState(false)

  // Check API key presence on mount
  useEffect(() => {
    fetch(`${API_BASE}/reports/deepseek/status`)
      .then((r) => r.json())
      .then((d) => setMissingKey(!d.apiKeyPresent))
      .catch(() => {})
  }, [])

  // Load cached report when alert changes
  useEffect(() => {
    if (!alertId) {
      setState({ status: "idle" })
      return
    }

    setState({ status: "checking" })

    fetch(`${API_BASE}/reports/deepseek/${encodeURIComponent(alertId)}`, {
      headers: authHeaders,
    })
      .then(async (r) => {
        if (r.status === 404) {
          setState({ status: "no_report" })
          return
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data: ReportEnvelope = await r.json()
        setState({ status: "ready", data })
      })
      .catch(() => setState({ status: "no_report" }))
  }, [alertId])

  const generate = useCallback(
    async (force = false) => {
      if (!alertId) return
      setState({ status: "generating" })
      try {
        const r = await fetch(
          `${API_BASE}/reports/deepseek/${encodeURIComponent(alertId)}?force=${force}`,
          { method: "POST", headers: authHeaders }
        )
        const body = await r.json()
        if (!r.ok) {
          const msg: string = body?.detail ?? `HTTP ${r.status}`
          setState({
            status: "error",
            message: msg.includes("OPENROUTER_API_KEY")
              ? "OpenRouter API key is missing. Add OPENROUTER_API_KEY to backend/.env and restart backend."
              : msg.toLowerCase().includes("invalid api key") || r.status === 401
              ? "Sentinel backend API key missing or invalid. Check NEXT_PUBLIC_ADMIN_API_KEY in .env.local and restart frontend."
              : msg,
          })
          return
        }
        setState({ status: "ready", data: body as ReportEnvelope })
      } catch {
        setState({
          status: "error",
          message: "Network error — is the backend running?",
        })
      }
    },
    [alertId]
  )

  const copyReport = useCallback(async () => {
    if (state.status !== "ready") return
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(state.data.report, null, 2)
      )
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {}
  }, [state])

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden flex flex-col h-full shadow-inner">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center gap-2 border-b border-border px-4 py-2.5 bg-muted/20">
        <FileSearch className="h-3.5 w-3.5 text-primary" />
        <span className="text-xs font-semibold text-foreground">
          DeepSeek Incident Report
        </span>
        <div className="ml-auto flex items-center gap-1.5 border border-primary/20 bg-primary/5 px-2 py-0.5 rounded-md">
          <Sparkles className="h-3 w-3 text-primary" />
          <span className="font-mono text-[9px] text-primary uppercase tracking-wider font-bold">
            DeepSeek via OpenRouter
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-4">
        {/* Missing key banner */}
        {missingKey && (
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-400" />
            <p className="text-[11px] leading-relaxed text-amber-300 font-medium">
              OpenRouter API key is missing. Add{" "}
              <code className="font-mono">OPENROUTER_API_KEY</code> to{" "}
              <code className="font-mono">backend/.env</code> and restart
              backend.
            </p>
          </div>
        )}

        {state.status === "idle" && (
          <div className="flex h-full flex-col items-center justify-center gap-2 py-6 text-center text-muted-foreground/50 border border-dashed border-border/70 rounded-lg">
            <FileSearch className="h-8 w-8 opacity-40" />
            <p className="text-xs font-medium">
              Select an incident to generate a report.
            </p>
          </div>
        )}

        {state.status === "checking" && (
          <div className="flex h-full items-center justify-center gap-2 text-muted-foreground/60">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-xs">Loading…</span>
          </div>
        )}

        {state.status === "no_report" && (
          <div className="flex h-full flex-col items-center justify-center gap-4 py-8 text-center border border-dashed border-border/70 rounded-lg">
            <FileSearch className="h-8 w-8 text-muted-foreground/40" />
            <div>
              <p className="text-xs font-medium text-foreground">
                No report for this incident yet.
              </p>
              <p className="mt-1 text-[10px] text-muted-foreground">
                DeepSeek will analyse the alert metadata and generate a
                structured forensic report.
              </p>
            </div>
            <button
              onClick={() => generate(false)}
              disabled={missingKey}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors",
                missingKey
                  ? "bg-muted text-muted-foreground cursor-not-allowed"
                  : "bg-primary text-primary-foreground hover:bg-primary/90"
              )}
            >
              <Sparkles className="h-3.5 w-3.5" />
              Generate DeepSeek Report
            </button>
          </div>
        )}

        {state.status === "generating" && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center py-4">
            <div className="relative flex h-10 w-10 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/20" />
              <Loader2 className="relative h-5 w-5 text-primary animate-spin" />
            </div>
            <div>
              <p className="text-xs font-semibold text-foreground">
                Contacting DeepSeek via OpenRouter…
              </p>
              <p className="mt-1 text-[10px] text-muted-foreground leading-relaxed">
                Generating structured incident report. This may take up to 45
                seconds.
              </p>
            </div>
          </div>
        )}

        {state.status === "error" && (
          <div className="space-y-3">
            <div className="flex items-start gap-2.5 rounded-lg border border-destructive/20 bg-destructive/5 p-3.5">
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-destructive" />
              <p className="text-[11px] leading-relaxed text-destructive/90 font-medium">
                {state.message}
              </p>
            </div>
            {alertId && (
              <button
                onClick={() => generate(false)}
                className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted/50 transition-colors"
              >
                <RefreshCw className="h-3 w-3" />
                Try again
              </button>
            )}
          </div>
        )}

        {state.status === "ready" && (
          <div className="space-y-4">
            {/* Action bar */}
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={() => generate(true)}
                className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[11px] font-medium hover:bg-muted/50 transition-colors"
              >
                <RefreshCw className="h-3 w-3" />
                Regenerate
              </button>
              <button
                onClick={copyReport}
                className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-[11px] font-medium hover:bg-muted/50 transition-colors"
              >
                {copied ? (
                  <>
                    <ClipboardCheck className="h-3 w-3 text-green-500" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    Copy Report
                  </>
                )}
              </button>
              <span className="ml-auto text-[9px] text-muted-foreground font-mono">
                {state.data.model} ·{" "}
                {new Date(state.data.generated_at).toLocaleTimeString()}
              </span>
            </div>

            {/* Report sections */}
            <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/5 p-3.5">
              {state.data.report.raw && (
                <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-[10px] text-amber-300">
                  Note: Model returned unstructured text — displaying as-is.
                </div>
              )}

              {state.data.report.executive_summary && (
                <Section label="Executive Summary">
                  {state.data.report.executive_summary}
                </Section>
              )}

              {/* v2: incident_classification | v1 fallback: incident_type + severity_assessment */}
              {state.data.report.incident_classification ? (
                <Section label="Incident Classification">
                  {state.data.report.incident_classification}
                </Section>
              ) : (state.data.report.incident_type || state.data.report.severity_assessment) ? (
                <div className="grid grid-cols-2 gap-3">
                  {state.data.report.incident_type && (
                    <Section label="Incident Type">
                      {state.data.report.incident_type}
                    </Section>
                  )}
                  {state.data.report.severity_assessment && (
                    <Section label="Severity">
                      {state.data.report.severity_assessment}
                    </Section>
                  )}
                </div>
              ) : null}

              {/* v2: source_and_evidence | v1 fallback: camera_source + observed_evidence */}
              {state.data.report.source_and_evidence ? (
                <Section label="Source & Evidence">
                  {state.data.report.source_and_evidence}
                </Section>
              ) : (
                <>
                  {state.data.report.camera_source && (
                    <Section label="Camera / Location">
                      {state.data.report.camera_source}
                    </Section>
                  )}
                  {state.data.report.observed_evidence && (
                    <Section label="Observed Evidence">
                      {state.data.report.observed_evidence}
                    </Section>
                  )}
                </>
              )}

              {/* v2: confidence_analysis | v1 fallback: confidence_interpretation */}
              {(state.data.report.confidence_analysis || state.data.report.confidence_interpretation) && (
                <Section label="Confidence Analysis">
                  {state.data.report.confidence_analysis || state.data.report.confidence_interpretation}
                </Section>
              )}

              {toLines(state.data.report.timeline).length > 0 && (
                <Section label="Timeline">
                  <ul className="list-disc list-inside space-y-0.5">
                    {toLines(state.data.report.timeline).map((t, i) => (
                      <li key={i}>{t}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {state.data.report.behavioral_interpretation && (
                <Section label="Behavioral Interpretation">
                  {state.data.report.behavioral_interpretation}
                </Section>
              )}

              {state.data.report.risk_assessment && (
                <Section label="Risk Assessment">
                  {state.data.report.risk_assessment}
                </Section>
              )}

              {/* v2: operator_actions | v1 fallback: recommended_actions */}
              {toLines(
                state.data.report.operator_actions ?? state.data.report.recommended_actions
              ).length > 0 && (
                <Section label="Operator Actions">
                  <ul className="list-disc list-inside space-y-0.5">
                    {toLines(
                      state.data.report.operator_actions ?? state.data.report.recommended_actions
                    ).map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {toLines(state.data.report.limitations).length > 0 && (
                <Section label="Limitations">
                  <ul className="list-disc list-inside space-y-0.5 text-muted-foreground">
                    {toLines(state.data.report.limitations).map((l, i) => (
                      <li key={i}>{l}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {state.data.report.final_verdict && (
                <Section label="Final Verdict">
                  <span className="font-semibold">
                    {state.data.report.final_verdict}
                  </span>
                </Section>
              )}

              {/* v2: demo_explanation | v1 fallback: demo_notes_for_graduation_committee */}
              {(state.data.report.demo_explanation || state.data.report.demo_notes_for_graduation_committee) && (
                <details>
                  <summary className="cursor-pointer text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60 hover:text-muted-foreground transition-colors">
                    Demo Notes ▸
                  </summary>
                  <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
                    {state.data.report.demo_explanation || state.data.report.demo_notes_for_graduation_committee}
                  </p>
                </details>
              )}
            </div>

            <p className="flex items-center gap-1.5 text-[9px] text-muted-foreground font-medium pt-1 border-t border-border/50">
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
              Generated by DeepSeek via OpenRouter from alert metadata only.
              Evidence based on system records.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
