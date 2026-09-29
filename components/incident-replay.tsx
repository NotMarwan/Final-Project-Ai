"use client"

import { useEffect, useRef, useState } from "react"
import { Film, Loader2, Maximize2, Pause, Play, RotateCcw, Volume2, VolumeX } from "lucide-react"
import type { ThreatBox } from "@/lib/detection-types"
import { getContainedVideoRect, projectOverlayBox } from "@/lib/live-visual-state"
import { apiFetch } from "@/lib/api-auth"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const MAX_AUTO_RETRIES = 10
const RETRY_MS = 2_000
export type EvidenceStatus = "unavailable" | "loading" | "ready" | "error"

interface IncidentReplayProps {
  alertId?: string
  clipUrl?: string
  thumbnailUrl?: string
  threatType: "violence" | "weapon"
  confidence: number
  location: string
  timestamp: string
  onClose?: () => void
  className?: string
  autoPlay?: boolean
  maxDuration?: number
  threatBoxes?: ThreatBox[]
  alertVideoWidth?: number
  alertVideoHeight?: number
  detectionOffsetSeconds?: number
  onStatusChange?: (status: EvidenceStatus) => void
}

function formatSeconds(value: number) {
  if (!Number.isFinite(value) || value < 0) return "0:00"
  return String(Math.floor(value / 60)) + ":" + String(Math.floor(value % 60)).padStart(2, "0")
}

export function IncidentReplay({
  alertId, clipUrl, thumbnailUrl, threatType, confidence, location, timestamp,
  onClose, className = "", autoPlay = false, maxDuration, threatBoxes,
  alertVideoWidth, alertVideoHeight, detectionOffsetSeconds, onStatusChange,
}: IncidentReplayProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const frameRef = useRef<HTMLDivElement>(null)
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [status, setStatus] = useState<EvidenceStatus>("unavailable")
  const [attempt, setAttempt] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(true)
  const [time, setTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const validId = Boolean(alertId && /^[A-Za-z0-9_-]{1,128}$/.test(alertId))
  const path = validId ? "/clips/" + encodeURIComponent(alertId as string)
    : clipUrl && /^\/clips\/[A-Za-z0-9_-]{1,128}$/.test(clipUrl) ? clipUrl : null

  useEffect(() => { onStatusChange?.(status) }, [status, onStatusChange])
  useEffect(() => {
    if (!path) return
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    let url: string | undefined
    const load = async (number: number) => {
      setStatus("loading")
      try {
        const response = await apiFetch(API_BASE + path)
        if (!response.ok) {
          if (response.status === 404 && number < MAX_AUTO_RETRIES) {
            timer = setTimeout(() => { if (active) void load(number + 1) }, RETRY_MS)
            return
          }
          throw new Error("evidence unavailable")
        }
        url = URL.createObjectURL(await response.blob())
        if (active) { setObjectUrl(url); setStatus("ready") }
        else URL.revokeObjectURL(url)
      } catch { if (active) setStatus("error") }
    }
    void load(0)
    return () => {
      active = false
      if (timer) clearTimeout(timer)
      if (url) URL.revokeObjectURL(url)
    }
  }, [path, attempt])
  useEffect(() => {
    const node = frameRef.current
    if (!node) return
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }))
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const togglePlay = async () => {
    const video = videoRef.current
    if (!video || status !== "ready") return
    if (video.paused) {
      try { await video.play(); setPlaying(true) } catch { setPlaying(false) }
    } else { video.pause(); setPlaying(false) }
  }
  const detectionKnown = typeof detectionOffsetSeconds === "number"
    && Number.isFinite(detectionOffsetSeconds) && detectionOffsetSeconds >= 0
    && duration > 0 && detectionOffsetSeconds <= duration
  const showBoxes = detectionKnown && Math.abs(time - detectionOffsetSeconds) < 0.7
  const videoWidth = alertVideoWidth ?? videoRef.current?.videoWidth ?? 0
  const videoHeight = alertVideoHeight ?? videoRef.current?.videoHeight ?? 0
  const rect = videoWidth > 0 && videoHeight > 0
    ? getContainedVideoRect(size.width, size.height, videoWidth, videoHeight) : null

  return <section className={"overflow-hidden rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-0)] " + className} aria-label="مراجعة الدليل المصور">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-hairline)] px-4 py-3">
      <div className="flex items-center gap-2"><Film size={16} className="text-[var(--signal)]" /><strong className="text-sm">مراجعة المقطع</strong></div>
      <span className="rounded border border-[var(--state-replay)]/40 bg-[var(--surface-2)] px-2 py-1 text-[10px] text-[var(--state-replay)]">دليل مسجل · ليس بثاً حياً</span>
    </div>
    <div ref={frameRef} dir="ltr" className="relative flex aspect-video max-h-[400px] min-h-[230px] items-center justify-center overflow-hidden bg-[var(--surface-0)]">
      {objectUrl && <video
        ref={videoRef} src={objectUrl} poster={thumbnailUrl} playsInline muted={muted}
        className="h-full w-full object-contain"
        onLoadedMetadata={(event) => {
          setDuration(event.currentTarget.duration || 0)
          if (autoPlay) void event.currentTarget.play().then(() => setPlaying(true)).catch(() => setPlaying(false))
        }}
        onTimeUpdate={(event) => {
          setTime(event.currentTarget.currentTime)
          if (maxDuration !== undefined && event.currentTarget.currentTime >= maxDuration) { event.currentTarget.pause(); setPlaying(false) }
        }}
        onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onError={() => setStatus("error")}
      />}
      {showBoxes && rect && threatBoxes?.map((box) => {
        const [x1, y1, x2, y2] = projectOverlayBox(box.bbox, rect, videoWidth, videoHeight)
        return <div key={box.id} className="pointer-events-none absolute border-2 border-[var(--threat-critical)]" style={{ insetInlineStart: x1, top: y1, width: x2 - x1, height: y2 - y1 }} />
      })}
      {status !== "ready" && <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-5 text-center" role="status">
        <div className="grid size-16 place-items-center rounded-full border border-[var(--border-hairline)] bg-[var(--surface-1)] text-[var(--text-tertiary)]">
          {status === "loading" ? <Loader2 size={25} className="animate-spin motion-reduce:animate-none" /> : <Film size={25} />}
        </div>
        <strong className="text-sm text-[var(--text-primary)]">{status === "loading" ? "جارٍ التحقق من المقطع المسجل" : status === "error" ? "تعذر تحميل الدليل المصور" : "لا يوجد مقطع دليل لهذه الحادثة"}</strong>
        <span className="max-w-sm text-xs leading-6 text-[var(--text-tertiary)]">{status === "loading" ? "قد يستغرق حفظ المقطع وقتاً قصيراً بعد التنبيه." : "تبقى بيانات التنبيه متاحة للمراجعة، ولا يعني غياب المقطع عدم وقوع الحادثة."}</span>
        {status === "error" && <button type="button" onClick={() => setAttempt((value) => value + 1)} className="rounded border border-[var(--border-hairline)] px-3 py-1.5 text-xs text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]">إعادة المحاولة</button>}
      </div>}
    </div>
    <div className="space-y-3 border-t border-[var(--border-hairline)] px-4 py-3">
      <div className="relative">
        {detectionKnown && <span className="pointer-events-none absolute -top-1 h-4 w-0.5 bg-[var(--threat-critical)]" style={{ insetInlineStart: String((detectionOffsetSeconds / duration) * 100) + "%" }} title="لحظة الكشف" />}
        <input type="range" min={0} max={duration || 1} step={0.05} value={Math.min(time, duration || 1)}
          onChange={(event) => { if (videoRef.current) videoRef.current.currentTime = Number(event.target.value) }}
          disabled={status !== "ready"} dir="ltr" aria-label="الانتقال في المقطع"
          className="h-2 w-full cursor-pointer accent-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:cursor-not-allowed disabled:opacity-40" />
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => void togglePlay()} disabled={status !== "ready"} aria-label={playing ? "إيقاف مؤقت" : "تشغيل"} className="grid size-8 place-items-center rounded bg-[var(--surface-2)] hover:bg-[var(--surface-3)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40">{playing ? <Pause size={15} /> : <Play size={15} />}</button>
          <button type="button" onClick={() => { if (videoRef.current) { videoRef.current.currentTime = 0; setTime(0) } }} disabled={status !== "ready"} aria-label="العودة إلى البداية" className="grid size-8 place-items-center rounded text-[var(--text-secondary)] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40"><RotateCcw size={15} /></button>
          <bdi className="instrument-num text-[11px] text-[var(--text-secondary)]">{formatSeconds(time)} / {formatSeconds(duration)}</bdi>
        </div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setMuted((value) => !value)} disabled={status !== "ready"} aria-label={muted ? "تشغيل الصوت" : "كتم الصوت"} className="grid size-8 place-items-center rounded text-[var(--text-secondary)] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40">{muted ? <VolumeX size={15} /> : <Volume2 size={15} />}</button>
          <button type="button" onClick={() => void frameRef.current?.requestFullscreen()} disabled={status !== "ready"} aria-label="ملء الشاشة" className="grid size-8 place-items-center rounded text-[var(--text-secondary)] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40"><Maximize2 size={15} /></button>
          {onClose && <button type="button" onClick={onClose} className="rounded px-2 py-1 text-xs text-[var(--text-secondary)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]">إغلاق</button>}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-1 text-[10px] text-[var(--text-tertiary)]">
        <span>{detectionKnown ? "العلامة الحمراء: لحظة الكشف" : "موضع لحظة الكشف داخل المقطع غير متوفر في بيانات التنبيه"}</span>
        <span><bdi>{threatType === "weapon" ? "سلاح" : "اعتداء"}</bdi> · درجة النموذج <bdi>{Number.isFinite(confidence) && confidence >= 0 && confidence <= 100 ? confidence.toFixed(1) + "%" : "غير متوفر"}</bdi> غير معايرة · {location || "الموقع غير متوفر"} · <bdi>{timestamp || "الوقت غير متوفر"}</bdi></span>
      </div>
    </div>
  </section>
}
