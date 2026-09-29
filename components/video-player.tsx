"use client"

import { memo, useEffect, useRef, useState } from "react"
import { CameraOff, EyeOff, Pause, Play, RefreshCw, WifiOff } from "lucide-react"
import type { DetectionCategory, CategoryScore } from "@/lib/detection-types"
import { WebRTCPlayer } from "@/components/webrtc-player"
import { CanvasOverlay } from "@/components/canvas-overlay"
import { useDetectionStream } from "@/hooks/use-detection-stream"
import type { OverlaySettings } from "@/components/overlay-settings"
import { MultiThreatBanner } from "@/components/multi-threat-banner"
import { ConfidenceBars } from "@/components/confidence-bars"
import { PipelineTelemetryPanel } from "@/components/pipeline-telemetry"
import { normalizeScoreToPercent, sourceVisualState, type SourceVisualState } from "@/lib/live-visual-state"
import { reconnectDelayMs } from "@/lib/reconnect-backoff"
import { apiFetch } from "@/lib/api-auth"
import { formatTime24 } from "@/components/shell/locale"

export interface FaceObservation {
  id: string
  label: string
  kind: "known" | "unknown"
  confidence: number
  bbox: number[]
}

export interface FaceUnknownDetail {
  id: string
  firstSeenFrame: number
  lastSeenFrame: number
  durationFrames: number
  firstSeenAt: string
  lastSeenAt: string
  hitStreak: number
  lastBbox: number[]
}

export interface FaceSummaryPayload {
  enabled: boolean
  identityLabelingEnabled?: boolean
  frameIndex?: number
  totalFaces: number
  recognized: Array<{ personId?: string; label?: string; confidence?: number; distance?: number }>
  recognizedCount?: number
  unknownIds: string[]
  unknownCount: number
  unknownDetails?: FaceUnknownDetail[]
  observations?: FaceObservation[]
}

export interface LiveAlert {
  id: string
  timestamp: string
  isoTime: string
  confidence: number
  modelConfidence?: number
  rawModelConfidence?: number | null
  threatConfidence?: number
  type: "Violence" | "Weapon"
  severity: "critical" | "high" | "medium"
  cameraId: string
  location: string
  fusionScore?: number
  fusionModel?: string
  motionScore?: number
  weaponScore?: number
  weaponLabels?: string[]
  weaponDetectorReady?: boolean
  fusionReason?: string
  faceSummary?: FaceSummaryPayload
  clipUrl?: string
  categories?: CategoryScore[]
  primaryCategory?: DetectionCategory
  allCategories?: DetectionCategory[]
  threatType?: "violence" | "weapon"
  alertLatencyMs?: number
  personCount?: number
  weaponBbox?: [number, number, number, number]
  violenceBbox?: [number, number, number, number]
  alertVideoWidth?: number
  alertVideoHeight?: number
  /** WT-20 SC-4 additive (wired by WT-17): precise score semantics — displays must
   * distinguish calibrated probability vs raw model score vs severity. */
  scoreSemantics?: Record<string, string>
  scoreSource?: "violence" | "weapon" | "unknown"
  rawModelScore?: number | null
  calibratedProbability?: number | null
  confirmedAlert?: boolean
  alertState?: string
  calibrationStatus?: string
  severitySource?: string
}

type CameraId = "CAM-01" | "CAM-02" | "EXAMPLE-01" | "EXAMPLE-02" | "EXAMPLE-03"
type Props = {
  cameraId: CameraId
  activeAlert: LiveAlert | null
  privacyMode: boolean
  personCount?: number
  overlaySettings?: OverlaySettings
  onSourceStateChange?: (state: SourceVisualState) => void
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const LIVE_DEMO_URL = process.env.NEXT_PUBLIC_LIVE_DEMO_URL ?? ""
const DEMO_LOADING_MS = 4_000
const ALERT_LINGER_MS = 8_000
const STATE_COPY: Record<SourceVisualState, string> = {
  live: "مباشر", replay: "إعادة تشغيل", stale: "بيانات قديمة", offline: "متوقف", loading: "جارٍ الاتصال", unverified: "مصدر غير موثق",
}
const STATE_TOKEN: Record<SourceVisualState, string> = {
  live: "var(--state-live)", replay: "var(--state-replay)", stale: "var(--state-stale)", offline: "var(--state-offline)", loading: "var(--state-stale)", unverified: "var(--state-stale)",
}

export const VideoPlayer = memo(function VideoPlayer({ cameraId, activeAlert, privacyMode, overlaySettings, onSourceStateChange }: Props) {
  const isDemo = cameraId.startsWith("EXAMPLE-")
  const externalPlayback = LIVE_DEMO_URL.trim().length > 0
  const [isPlaying, setIsPlaying] = useState(true)
  const [streamError, setStreamError] = useState(false)
  const [frameReady, setFrameReady] = useState(false)
  const [streamKey, setStreamKey] = useState(0)
  // WT-17 (S-09): stream health — heartbeat stall detection + backoff auto-restart.
  const [streamStalled, setStreamStalled] = useState(false)
  const lastFrameAtRef = useRef<number>(0)
  const loadCountRef = useRef(0)
  const restartAttemptRef = useRef(0)
  const restartTimerRef = useRef<number | null>(null)
  const [demoLoading, setDemoLoading] = useState(isDemo)
  const [webrtcUrl, setWebrtcUrl] = useState<string | null>(null)
  const [webrtcReady, setWebrtcReady] = useState(false)
  const [webrtcFailed, setWebrtcFailed] = useState(false)
  const [alertVisible, setAlertVisible] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const { data, overlayRef, telemetry, history, connected, stale, inferenceStale, error, now } = useDetectionStream(cameraId)
  const visualState = sourceVisualState({ connected, stale: stale || streamStalled, inferenceStale, frameReady, failed: streamError || (isDemo && !demoLoading && !connected && !frameReady), sourceKind: telemetry?.sourceKind ?? null, isDemo, externalPlayback })
  const detectionAvailable = connected && !stale && !inferenceStale && !externalPlayback
  const detectionData = detectionAvailable ? data : null
  const decisionState = detectionAvailable ? telemetry?.decisionState : null
  const confirmed = decisionState === "CONFIRMED" && (visualState === "live" || visualState === "replay")
  const hasViolence = confirmed && Boolean(detectionData?.multiThreat?.hasViolence)
  const hasWeapon = confirmed && Boolean(detectionData?.multiThreat?.hasWeapon)
  const isCriticalNow = confirmed && (detectionData?.multiThreat?.severity === "critical" || (alertVisible && activeAlert?.severity === "critical"))
  const violenceScore = telemetry?.violenceScore != null ? telemetry.violenceScore * 100 : normalizeScoreToPercent(detectionData?.multiThreat?.violenceScore)
  const weaponScore = telemetry?.weaponScore != null ? telemetry.weaponScore * 100 : normalizeScoreToPercent(detectionData?.multiThreat?.weaponScore)
  const sourceTone = STATE_TOKEN[visualState]
  const settings = overlaySettings

  useEffect(() => { onSourceStateChange?.(visualState) }, [visualState, onSourceStateChange])
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const measure = () => { const rect = el.getBoundingClientRect(); setSize({ width: rect.width, height: rect.height }) }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    if (!isDemo) return
    const timer = window.setTimeout(() => setDemoLoading(false), DEMO_LOADING_MS)
    return () => window.clearTimeout(timer)
  }, [isDemo, cameraId])
  useEffect(() => {
    let cancelled = false
    apiFetch(`${API_BASE}/api/webrtc/${encodeURIComponent(cameraId)}`)
      .then((response) => { if (!response.ok) throw new Error("WebRTC unavailable"); return response.json() })
      .then((result) => { if (!cancelled && typeof result.url === "string") setWebrtcUrl(result.url) })
      .catch(() => { if (!cancelled) setWebrtcFailed(true) })
    return () => { cancelled = true }
  }, [cameraId])
  useEffect(() => {
    if (!activeAlert || activeAlert.cameraId !== cameraId) return
    const age = Date.now() - Date.parse(activeAlert.isoTime)
    if (!Number.isFinite(age) || age < 0 || age > ALERT_LINGER_MS) return
    const start = window.setTimeout(() => setAlertVisible(true), 0)
    const end = window.setTimeout(() => setAlertVisible(false), ALERT_LINGER_MS - age)
    return () => { window.clearTimeout(start); window.clearTimeout(end) }
  }, [activeAlert, cameraId])
  // WT-17 (S-09): heartbeat watchdog — a silent stall must not look like a healthy
  // stream. Load-event cadence for multipart <img> differs per browser: once >2
  // loads prove per-frame cadence, enforce the 3s heartbeat fully; until then only
  // "no first frame" is treated as stalled (documented limitation otherwise).
  useEffect(() => {
    if (isDemo || externalPlayback || !isPlaying) return
    const interval = window.setInterval(() => {
      const last = lastFrameAtRef.current
      const gap = last ? Date.now() - last : Number.POSITIVE_INFINITY
      const stalled = gap > 3_000 && (loadCountRef.current > 2 || loadCountRef.current === 0)
      setStreamStalled(stalled)
      if (stalled) scheduleStreamRestart()
    }, 1_000)
    return () => window.clearInterval(interval)
  }, [isDemo, externalPlayback, isPlaying])

  // WT-17 (S-09): <img> stream handlers — every painted frame resets the heartbeat.
  const handleStreamFrame = () => {
    lastFrameAtRef.current = Date.now()
    loadCountRef.current += 1
    restartAttemptRef.current = 0
    setStreamStalled(false)
    setFrameReady(true)
  }
  const scheduleStreamRestart = () => {
    if (restartTimerRef.current !== null) return
    restartAttemptRef.current += 1
    const delay = reconnectDelayMs(restartAttemptRef.current)
    restartTimerRef.current = window.setTimeout(() => {
      restartTimerRef.current = null
      setStreamError(false)
      setStreamKey((key) => key + 1)
    }, delay)
  }
  const handleStreamError = () => {
    setStreamError(true)
    setFrameReady(false)
    scheduleStreamRestart()
  }
  const retry = () => {
    if (restartTimerRef.current !== null) { window.clearTimeout(restartTimerRef.current); restartTimerRef.current = null }
    restartAttemptRef.current = 0
    setStreamStalled(false)
    setStreamError(false)
    setFrameReady(false)
    setStreamKey((key) => key + 1)
  }
  const streamSrc = `${API_BASE}/video_feed?camera_id=${encodeURIComponent(cameraId)}&k=${streamKey}`
  const demoSrc = isDemo && !demoLoading ? streamSrc : undefined
  const showOffline = streamError || visualState === "offline"
  const statusLine = !detectionAvailable ? telemetry && (stale || inferenceStale) ? "قراءات التحليل قديمة" : "التحليل غير متاح" : decisionState === "CONFIRMED" ? "تنبيه مؤكّد من محرك القرار" : decisionState === "WATCH" ? "جارٍ تقييم الرصد" : decisionState === "COOLDOWN" ? "فترة تهدئة التنبيهات" : decisionState === "NORMAL" ? "لا يوجد تنبيه مؤكّد" : "حالة القرار غير متاحة"
  const freshnessSeconds = telemetry?.updatedAt != null && now >= telemetry.updatedAt ? Math.floor((now - telemetry.updatedAt) / 1000) : null

  return <div className="flex h-full min-h-0 flex-col bg-[var(--surface-1)]">
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-hairline)] bg-[var(--surface-2)] px-4 py-2 text-[11px]"><span className="flex items-center gap-2 font-semibold" style={{ color: confirmed ? "var(--threat-critical)" : "var(--text-secondary)" }}><span className="size-1.5 rounded-full bg-current" />{statusLine}</span><span className="flex items-center gap-2 text-[var(--text-tertiary)]"><bdi className="instrument-num" dir="ltr">{cameraId}</bdi><span className="h-3 w-px bg-[var(--border-hairline)]" /><span style={{ color: sourceTone }}>{STATE_COPY[visualState]}</span></span></div>
    <div ref={containerRef} className={`relative min-h-[350px] flex-1 overflow-hidden bg-[var(--surface-0)] ${isCriticalNow ? "ring-2 ring-inset ring-[var(--threat-critical)]" : ""}`}>
      <div className="pointer-events-none absolute inset-0 opacity-20 [background-image:linear-gradient(var(--border-hairline)_1px,transparent_1px),linear-gradient(90deg,var(--border-hairline)_1px,transparent_1px)] [background-size:32px_32px]" />
      <div className="pointer-events-none absolute inset-0 m-auto size-44 rounded-full border border-[var(--border-hairline)] opacity-30 before:absolute before:inset-8 before:rounded-full before:border before:border-[var(--border-hairline)] after:absolute after:inset-1/2 after:h-px after:w-12 after:-translate-x-1/2 after:bg-[var(--border-hairline)]" />
      {isDemo && demoSrc && !streamError && <img key={demoSrc} src={demoSrc} alt={`إعادة تشغيل ${cameraId}`} className="absolute inset-0 size-full object-contain" onLoad={handleStreamFrame} onError={handleStreamError} />}
      {!isDemo && !externalPlayback && !streamError && <div className="absolute inset-0"><img key={streamSrc} src={isPlaying ? streamSrc : undefined} alt={`بث الكاميرا ${cameraId}`} className={`size-full object-contain ${webrtcReady ? "invisible" : "visible"}`} onLoad={handleStreamFrame} onError={handleStreamError} />{webrtcUrl && !webrtcFailed && <WebRTCPlayer streamUrl={webrtcUrl} camId={cameraId} onError={() => setWebrtcFailed(true)} onConnected={() => { setWebrtcReady(true); setFrameReady(true); setStreamError(false) }} className={`absolute inset-0 ${webrtcReady ? "z-10" : "z-0"}`} />}</div>}
      {externalPlayback && <iframe title="إعادة تشغيل خارجية" src={LIVE_DEMO_URL} className="absolute inset-0 size-full border-0" allow="autoplay; fullscreen; picture-in-picture" referrerPolicy="no-referrer" onLoad={() => setFrameReady(true)} />}
      {/* WT-17 (S-09): <img> MJPEG exposes no display-side frame identity, so
          displayFrameSequence stays null and the overlay self-hides — a hidden
          overlay is never misaligned. Server-side annotate_fn carries overlays.
          Any identity-capable transport must pass its real displayFrameSequence. */}
      {frameReady && size.width > 0 && !externalPlayback && <CanvasOverlay displayFrameSequence={null} data={detectionData} dataRef={detectionAvailable ? overlayRef : undefined} videoWidth={detectionData?.videoWidth ?? 1280} videoHeight={detectionData?.videoHeight ?? 720} containerWidth={size.width} containerHeight={size.height} showBoxes={settings?.showBoxes ?? true} showLabels={settings?.showLabels ?? true} opacity={settings?.opacity ?? 85} boxThickness={settings?.boxThickness ?? 2} labelStyle={settings?.labelStyle ?? "chip"} />}
      {isCriticalNow && <div className="pointer-events-none absolute inset-0 z-20 animate-pulse border-[3px] border-[var(--threat-critical)]" aria-hidden="true" />}
      {settings?.showThreatBadge !== false && <MultiThreatBanner hasViolence={hasViolence} hasWeapon={hasWeapon} isMultiThreat={hasViolence && hasWeapon} violenceScore={violenceScore} weaponScore={weaponScore} severity={detectionData?.multiThreat?.severity ?? (alertVisible ? activeAlert?.severity : undefined) ?? "medium"} weaponType={detectionData?.multiThreat?.threatBoxes?.find((box) => box.type === "weapon")?.weaponType} cameraId={cameraId} />}
      <ConfidenceBars visible={hasViolence || hasWeapon} bars={[{ label: "اعتداء", value: violenceScore, color: "var(--cat-violence)" }, { label: "سلاح", value: weaponScore, color: "var(--cat-weapon)" }, { label: "مدمج", value: normalizeScoreToPercent(detectionData?.multiThreat?.fusedScore), color: "var(--signal)" }]} />
      {privacyMode && <div className="absolute inset-0 z-40 flex flex-col items-center justify-center gap-3 bg-[var(--surface-0)]/95 text-center backdrop-blur-xl"><EyeOff size={30} className="text-[var(--threat-critical)]" /><strong className="text-sm">وضع الخصوصية مفعّل</strong><span className="text-[11px] text-[var(--text-secondary)]">صورة المصدر محجوبة عن العرض</span></div>}
      {!privacyMode && (showOffline || demoLoading || !frameReady) && <div className="absolute inset-0 z-20 flex flex-col items-center justify-center px-6 text-center"><div className="grid size-16 place-items-center rounded-full border border-[var(--border-hairline)] bg-[var(--surface-1)] text-[var(--state-offline)]">{showOffline ? <WifiOff size={27} /> : <CameraOff size={27} />}</div><span className="mt-4 text-sm font-semibold">{demoLoading ? "جارٍ تجهيز المقطع التجريبي" : showOffline ? "المحرك غير متصل" : "بانتظار أول إطار"}</span><p className="mt-2 max-w-[360px] text-[11px] leading-5 text-[var(--text-secondary)]">{isDemo ? "يتطلب تشغيل العينة خدمة التحليل المحلية. ستظل النتائج مصنّفة كإعادة تشغيل." : "تحقق من اتصال الكاميرا وتشغيل خدمة التحليل المحلية لبدء العرض."}</p>{showOffline && <><code dir="ltr" className="instrument-num mt-3 rounded border border-[var(--border-hairline)] bg-[var(--surface-2)] px-2 py-1 text-[10px] text-[var(--text-tertiary)]">python backend/api.py</code><button onClick={retry} className="mt-4 inline-flex items-center gap-1.5 rounded border border-[var(--signal)] px-3 py-1.5 text-[11px] text-[var(--signal)] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-[var(--signal)]"><RefreshCw size={13} />إعادة المحاولة</button></>}</div>}
      {frameReady && !privacyMode && <><div className="pointer-events-none absolute start-3 top-3 z-20 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-primary)]">{settings?.showPersonCount !== false && detectionAvailable && telemetry?.health.person?.status === "OK" && <span className="rounded border border-[var(--border-hairline)] bg-[var(--surface-0)]/85 px-2 py-1">الأشخاص <bdi className="instrument-num" dir="ltr">{detectionData?.personCount ?? "—"}</bdi></span>}{settings?.showFps !== false && detectionAvailable && detectionData?.fps != null && <span className="instrument-num rounded border border-[var(--border-hairline)] bg-[var(--surface-0)]/85 px-2 py-1" dir="ltr">{detectionData.fps.toFixed(0)} FPS</span>}</div><div className="pointer-events-none absolute bottom-3 start-3 z-20 flex items-center gap-2 rounded border border-[var(--border-hairline)] bg-[var(--surface-0)]/85 px-2 py-1 text-[10px] text-[var(--text-secondary)]"><bdi className="instrument-num" dir="ltr">{cameraId}</bdi>{settings?.showTimestamp !== false && telemetry?.updatedAt != null && <><span className="h-3 w-px bg-[var(--border-hairline)]" /><bdi className="instrument-num" dir="ltr">{formatTime24(telemetry.updatedAt, true)}</bdi></>}{settings?.showThreatBadge !== false && <><span className="h-3 w-px bg-[var(--border-hairline)]" />{STATE_COPY[visualState]}</>}</div></>}
    </div>
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-[var(--border-hairline)] bg-[var(--surface-2)] px-4 py-2.5 text-[10px] text-[var(--text-tertiary)]"><span className="text-[var(--text-secondary)]">قياسات التشغيل</span><span><bdi className="instrument-num text-[var(--text-primary)]" dir="ltr">{detectionAvailable && detectionData?.fps != null ? detectionData.fps.toFixed(0) : "—"}</bdi> <bdi dir="ltr">FPS</bdi></span><span>زمن المعالجة <bdi className="instrument-num text-[var(--text-primary)]" dir="ltr">{detectionAvailable && telemetry?.latencyMs != null ? `${telemetry.latencyMs.toFixed(0)} ms` : "—"}</bdi></span><span>عمر البيانات <bdi className="instrument-num text-[var(--text-primary)]" dir="ltr">{freshnessSeconds !== null ? `${freshnessSeconds} s` : "—"}</bdi></span><span className="ms-auto" style={{ color: sourceTone }}>{STATE_COPY[visualState]}</span></div>
    <PipelineTelemetryPanel telemetry={externalPlayback ? null : telemetry} history={externalPlayback ? [] : history} connected={connected && !externalPlayback} stale={stale || externalPlayback} inferenceStale={inferenceStale} error={error} cameraId={cameraId} />
    <div className="flex items-center justify-between border-t border-[var(--border-hairline)] px-4 py-2"><span className="text-[10px] text-[var(--text-tertiary)]">{alertVisible && confirmed ? "آخر تنبيه وارد معروض على المشهد" : "الصورة والتحليل يعتمدان على المصدر المختار"}</span><button type="button" disabled={isDemo || externalPlayback || webrtcReady} onClick={() => setIsPlaying((playing) => !playing)} aria-label={isPlaying ? "إيقاف عرض الكاميرا مؤقتاً" : "استئناف عرض الكاميرا"} className="flex size-7 items-center justify-center rounded border border-[var(--border-hairline)] text-[var(--text-secondary)] hover:text-[var(--signal)] focus-visible:outline-2 focus-visible:outline-[var(--signal)] disabled:opacity-40">{isPlaying ? <Pause size={13} /> : <Play size={13} />}</button></div>
  </div>
})
