"use client"

import { useEffect, useState } from "react"
import { Activity, ChevronDown, ShieldCheck, Timer } from "lucide-react"
import { frameAgeAtDisplayMs, type PipelineTelemetry, type TelemetryPoint } from "@/lib/pipeline-telemetry"

type Props = {
  telemetry: PipelineTelemetry | null
  history: TelemetryPoint[]
  connected: boolean
  stale: boolean
  inferenceStale: boolean
  error: string | null
  cameraId: string
}

const STATE_LABEL = { NORMAL: "طبيعي", WATCH: "قيد التقييم", CONFIRMED: "تنبيه مؤكّد", COOLDOWN: "فترة تهدئة" }
const STATE_TONE = { NORMAL: "var(--state-live)", WATCH: "var(--threat-high)", CONFIRMED: "var(--threat-critical)", COOLDOWN: "var(--state-stale)" }
const HEALTH_LABEL: Record<string, string> = { capture: "الالتقاط", violence: "الاعتداء", weapon: "السلاح", person: "الأشخاص" }
const PERCENT = (value: number | null | undefined) => value == null ? "—" : `${(value * 100).toFixed(1)}%`
const MISSING = "غير متاح"
const formatMs = (value: number | null | undefined) => value == null ? MISSING : `${value.toFixed(1)} ms`
const formatCount = (value: number | null | undefined) => value == null ? MISSING : String(value)

/** One label/value cell for the stage, queue, counter and frame-age telemetry grid. */
function MetricCell({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <span className="flex items-baseline justify-between gap-2 rounded border border-[var(--border-hairline)] bg-[var(--surface-0)] px-2 py-1 text-[10px]">
    <span className="text-[var(--text-tertiary)]">{label}</span>
    <bdi className="instrument-num" dir="ltr" style={{ color: tone ?? "var(--text-secondary)" }}>{value}</bdi>
  </span>
}

function ScoreTrace({ label, metric, history, current, threshold, stale }: {
  label: string
  metric: "violence" | "weapon"
  history: TelemetryPoint[]
  current: number | null
  threshold: number | null
  stale: boolean
}) {
  const points = history.filter((point) => point[metric] !== null)
  const last = history.at(-1)?.time ?? 0
  const first = Math.max(history[0]?.time ?? last, last - 60_000)
  const span = Math.max(1_000, last - first)
  const x = (time: number) => 5 + (time - first) / span * 390
  const y = (score: number) => 57 - score * 50
  const traceStale = stale || (points.length > 0 && last - points[points.length - 1].time > 5_000)
  const tone = traceStale ? "var(--state-stale)" : metric === "weapon" ? "var(--cat-weapon)" : "var(--cat-violence)"
  const path = points.map((point, index) => `${index > 0 && point.time - points[index - 1].time <= 5_000 ? "L" : "M"}${x(point.time).toFixed(1)},${y(point[metric]!).toFixed(1)}`).join(" ")
  return <div className="min-w-0 rounded-md border border-[var(--border-hairline)] bg-[var(--surface-0)] p-3">
    <div className="flex items-center justify-between gap-2"><strong className="text-xs">{label}</strong><bdi className="instrument-num text-[13px]" dir="ltr" style={{ color: tone }}>{PERCENT(current)}</bdi></div>
    <div className="relative mt-2 h-14"><svg viewBox="0 0 400 64" preserveAspectRatio="none" className="h-full w-full" role="img" aria-label={`${label}: ${points.length} قياس، عتبة التأكيد ${PERCENT(threshold)}`}><path d="M5,7 H395 M5,32 H395 M5,57 H395" fill="none" stroke="var(--border-hairline)" strokeWidth=".7" />{threshold !== null && <path d={`M5,${y(threshold)} H395`} fill="none" stroke="var(--text-tertiary)" strokeDasharray="5 4" strokeWidth="1" />}<path d={path} fill="none" stroke={tone} strokeWidth="2" vectorEffect="non-scaling-stroke" />{points.length === 1 && <circle cx={x(points[0].time)} cy={y(points[0][metric]!)} r="2.5" fill={tone} />}</svg>{points.length === 0 && <span className="absolute inset-0 grid place-items-center text-[10px] text-[var(--text-tertiary)]">بانتظار قياسات النموذج</span>}</div>
    <p className="mt-1 text-[10px] text-[var(--text-tertiary)]"><bdi className="instrument-num" dir="ltr">{points.length}</bdi> قياس فعلي · الخط المتقطع عتبة التأكيد {PERCENT(threshold)}</p>
  </div>
}

export function PipelineTelemetryPanel({ telemetry, history, connected, stale, inferenceStale, error, cameraId }: Props) {
  const [displayClock, setDisplayClock] = useState(() => Date.now())
  useEffect(() => {
    const interval = setInterval(() => setDisplayClock(Date.now()), 1_000)
    return () => clearInterval(interval)
  }, [])
  const available = connected && !stale && telemetry !== null
  const decisionAvailable = available && !inferenceStale
  const state = decisionAvailable ? telemetry.decisionState : null
  const connectionLabel = !connected ? "غير متصل" : error ? "بيانات غير صالحة" : stale && telemetry ? "بيانات قديمة" : !telemetry ? "بانتظار البيانات" : inferenceStale ? "الاستدلال متأخر" : "البيانات حديثة"
  const collected = telemetry?.framesCollected ?? null
  const required = telemetry?.framesRequired ?? null
  const progress = collected !== null && required !== null && required > 0 ? Math.min(100, collected / required * 100) : null
  const pipeline = available ? telemetry.pipeline : null
  const displayAgeMs = available ? frameAgeAtDisplayMs(telemetry.updatedAt, displayClock) : null
  const syncedLabel = pipeline?.inferenceComputeSynced === true ? "متزامن CUDA" : pipeline?.inferenceComputeSynced === false ? "بدون مزامنة CUDA" : MISSING
  return <details className="group shrink-0 border-t border-[var(--border-hairline)] bg-[var(--surface-1)]">
    <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-2.5 text-[11px] focus-visible:outline-2 focus-visible:outline-[var(--signal)] [&::-webkit-details-marker]:hidden"><span className="flex items-center gap-2"><Activity size={14} className="text-[var(--signal)]" /><strong>تفاصيل خط التحليل</strong><bdi className="instrument-num text-[10px] text-[var(--text-tertiary)]" dir="ltr">{cameraId}</bdi></span><span className="flex items-center gap-2" style={{ color: decisionAvailable ? "var(--state-live)" : "var(--state-stale)" }}>{connectionLabel}<ChevronDown size={13} className="transition-transform duration-[var(--motion-fast)] motion-reduce:transition-none group-open:rotate-180" /></span></summary>
    <div className="space-y-2 border-t border-[var(--border-hairline)] p-3">
      <div className="grid gap-2 md:grid-cols-[minmax(165px,.7fr)_1fr_1fr]">
        <div className="rounded-md border border-[var(--border-hairline)] bg-[var(--surface-0)] p-3"><div className="flex items-center gap-1.5 text-[10px] text-[var(--text-tertiary)]"><ShieldCheck size={13} />قرار الرصد</div><strong className="mt-2 block text-[13px]" style={{ color: state ? STATE_TONE[state] : "var(--state-stale)" }}>{state ? STATE_LABEL[state] : "غير متاح"}</strong><p className="mt-2 text-[10px] leading-5 text-[var(--text-secondary)]">{state === "CONFIRMED" ? "أكّده محرك القرار" : telemetry?.confirmN != null && telemetry.confirmM != null ? <>التأكيد يتطلب <bdi className="instrument-num" dir="ltr">{telemetry.confirmN}/{telemetry.confirmM}</bdi> نوافذ</> : "بانتظار عقد القرار"}</p>{telemetry?.calibrationStatus && <p className="mt-2 text-[10px] text-[var(--threat-high)]">معايرة: <bdi dir="ltr">{telemetry.calibrationStatus}</bdi></p>}</div>
        <ScoreTrace label="درجة الاعتداء" metric="violence" history={history} current={decisionAvailable ? telemetry.violenceScore : null} threshold={telemetry?.confirmThreshold ?? null} stale={!decisionAvailable} />
        <ScoreTrace label="درجة السلاح" metric="weapon" history={history} current={decisionAvailable ? telemetry.weaponScore : null} threshold={telemetry?.weaponThreshold ?? null} stale={!decisionAvailable} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[10px] text-[var(--text-secondary)]"><span className="flex items-center gap-1"><Timer size={12} />نافذة الاستدلال: {progress === null ? "غير متاحة" : <><bdi className="instrument-num" dir="ltr">{collected}/{required}</bdi> إطار</>}</span>{progress !== null && <span role="progressbar" aria-label="إطارات نافذة الاستدلال" aria-valuemin={0} aria-valuemax={required!} aria-valuenow={Math.min(collected!, required!)} className="h-1.5 w-20 overflow-hidden rounded bg-[var(--surface-3)]"><span className="block h-full bg-[var(--signal)]" style={{ width: `${progress}%` }} /></span>}{telemetry?.windowSpanSeconds != null && <span>امتداد النافذة <bdi className="instrument-num" dir="ltr">{telemetry.windowSpanSeconds.toFixed(2)} s</bdi> {telemetry.windowClockSource === "file-media" ? "بتوقيت المقطع" : telemetry.windowClockSource === "monotonic-capture" ? "بتوقيت الالتقاط" : ""}</span>}{telemetry?.windowValid === false && <span className="text-[var(--threat-high)]">نافذة غير صالحة</span>}<span className="ms-auto">زمن المعالجة <bdi className="instrument-num" dir="ltr">{decisionAvailable && telemetry?.latencyMs != null ? `${telemetry.latencyMs.toFixed(0)} ms` : "—"}</bdi> · زمن وصول التنبيه غير مقاس</span></div>
      <div className="rounded-md border border-[var(--border-hairline)] bg-[var(--surface-1)] p-2">
        <div className="mb-1.5 flex items-center justify-between gap-2 text-[10px] text-[var(--text-tertiary)]"><span className="flex items-center gap-1.5"><Timer size={12} />قياسات المراحل والطوابير</span><bdi dir="ltr">{pipeline?.schemaVersion ?? MISSING}</bdi></div>
        <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
          <MetricCell label="عمر الإطار عند بدء الاستدلال" value={formatMs(pipeline?.frameAgeMs.atInferenceStart)} />
          <MetricCell label="عمر الإطار عند النشر" value={formatMs(pipeline?.frameAgeMs.atPublication)} />
          <MetricCell label="عمر الإطار عند العرض (ساعة المتصفح)" value={formatMs(displayAgeMs)} />
          <MetricCell label="عمر الإطار عند إرسال الكشف" value={formatMs(telemetry?.displayFrameAgeMs)} />
          <MetricCell label="ساعة قياس عمر الإرسال" value={telemetry?.displayFrameAgeClockBase ?? MISSING} />
          <MetricCell label="إطارات مُسقطة في العرض" value={formatCount(telemetry?.renderBacklogDroppedCount)} tone={telemetry?.renderBacklogDroppedCount ? "var(--threat-high)" : undefined} />
          <MetricCell label="تسلسل إطار العرض" value={formatCount(telemetry?.displayFrameSequence)} />
          <MetricCell label="قراءة الإطار" value={formatMs(pipeline?.stageMs.frameRead)} />
          <MetricCell label="من الالتقاط إلى الطابور" value={formatMs(pipeline?.stageMs.captureToQueue)} />
          <MetricCell label="التجهيز" value={formatMs(pipeline?.stageMs.preprocess)} />
          <MetricCell label="النقل بين العمليات (طابور + تسلسل)" value={formatMs(pipeline?.stageMs.enqueueToDequeue)} />
          <MetricCell label="انتظار الاستدلال" value={formatMs(pipeline?.stageMs.inferenceWait)} />
          <MetricCell label="حساب الاستدلال" value={formatMs(pipeline?.stageMs.inferenceCompute)} tone={pipeline?.inferenceComputeSynced === false ? "var(--threat-high)" : undefined} />
          <MetricCell label="مزامنة حساب الاستدلال" value={syncedLabel} tone={pipeline?.inferenceComputeSynced === true ? "var(--state-live)" : undefined} />
          <MetricCell label="عمق طابور الإطارات" value={formatCount(pipeline?.queues.frameDepth)} />
          <MetricCell label="إطارات مُسقَطة" value={formatCount(pipeline?.queues.frameQueueDropped)} tone={pipeline?.queues.frameQueueDropped ? "var(--threat-high)" : undefined} />
          <MetricCell label="إطارات مُسقَطة (قياس مستقل)" value={formatCount(pipeline?.queues.frameQueueDroppedDerived)} />
          <MetricCell label="عمق طابور النتائج" value={formatCount(pipeline?.queues.resultDepth)} />
          <MetricCell label="تراكم الإطارات" value={formatCount(pipeline?.queues.backlogFrames)} />
          <MetricCell label="مكتمل: الأشخاص" value={formatCount(pipeline?.counters.personCompletedCount)} />
          <MetricCell label="مكتمل: الاعتداء" value={formatCount(pipeline?.counters.violenceCompletedCount)} />
          <MetricCell label="مكتمل: السلاح" value={formatCount(pipeline?.counters.weaponCompletedCount)} />
          <MetricCell label="إطارات مقروءة" value={formatCount(pipeline?.counters.framesReadCount)} />
        </div>
        {pipeline === null && <p className="mt-1.5 text-[10px] text-[var(--state-stale)]">كتلة قياسات المراحل غير متاحة من الخادم؛ تُعرض القيم كغير متاحة لا كأصفار.</p>}
      </div>
      <div className="flex flex-wrap gap-1.5">{["capture", "violence", "weapon", "person"].map((name) => { const health = available ? telemetry?.health[name] : undefined; const label = health?.status === "OK" && inferenceStale && name !== "capture" ? "STALE" : health?.status ?? "UNAVAILABLE"; const tone = label === "OK" ? "var(--state-live)" : label === "FAILED" ? "var(--threat-critical)" : label === "DEGRADED" ? "var(--threat-high)" : "var(--state-stale)"; return <span key={name} title={health?.reason || undefined} className="rounded border border-[var(--border-hairline)] px-2 py-1 text-[10px]" style={{ color: tone }}>{HEALTH_LABEL[name]} · <bdi dir="ltr">{label}</bdi></span> })}</div>
      {!decisionAvailable && history.length > 0 && <p className="text-[10px] text-[var(--threat-high)]">القياسات السابقة محفوظة للمراجعة؛ لا تمثل رصداً حالياً.</p>}
    </div>
  </details>
}
