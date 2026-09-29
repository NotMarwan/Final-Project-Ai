"use client"

import type { LiveAlert } from "@/components/video-player"
import { SEVERITY_LABELS } from "@/lib/detection-types"
import { formatTime24 } from "@/components/shell/locale"
import type { TimeWindow } from "./overview-time"

const RIBBON_DURATION_MS = 30 * 60_000
const EVENT_WINDOW_MS = 2.5 * 60_000

export function HeroIncidentInstrument({ alerts, now, isOffline, selectedCamera, selectedWindow, onSelect, onHoverCamera }: {
  alerts: readonly LiveAlert[]
  now: number
  isOffline: boolean
  selectedCamera?: string
  selectedWindow: TimeWindow | null
  onSelect: (alert: LiveAlert, window: TimeWindow) => void
  onHoverCamera: (cameraId: string | null) => void
}) {
  const from = now - RIBBON_DURATION_MS
  const recent = alerts.filter((alert) => {
    const time = Date.parse(alert.isoTime)
    return Number.isFinite(time) && time >= from && time <= now
  })
  const cameraIds = [...new Set(recent.map((alert) => alert.cameraId))].sort()
  const shown = cameraIds.slice(0, 3)

  return <div className="hero-instrument" role="group" aria-label={`إشارات الكاميرات: ${recent.length} تنبيه خلال آخر 30 دقيقة، موزعة على ${cameraIds.length} كاميرات`}>
    <div className="hero-instrument-heading"><span>إشارات الكاميرات <bdi dir="ltr" className="instrument-num">/ 30 MIN</bdi></span><span className="hero-instrument-count">{isOffline ? "القناة غير متصلة" : <><bdi dir="ltr" className="instrument-num">{recent.length}</bdi> تنبيه مستلم</>}</span></div>
    {shown.length > 0 ? <>
      <div className="hero-ribbon-lanes" dir="ltr">{shown.map((cameraId) => {
        const laneAlerts = recent.filter((alert) => alert.cameraId === cameraId)
        return <div className="hero-ribbon-lane" key={cameraId} role="group" aria-label={`كاميرا ${cameraId}: ${laneAlerts.length} تنبيه خلال آخر 30 دقيقة`} onMouseEnter={() => onHoverCamera(cameraId)} onMouseLeave={() => onHoverCamera(null)}>
        <bdi className={`hero-ribbon-camera instrument-num ${selectedCamera === cameraId ? "is-selected" : ""}`}>{cameraId}<small> · {laneAlerts.length}</small></bdi>
        <div className="hero-ribbon-track">
          {laneAlerts.map((alert) => {
            const time = Date.parse(alert.isoTime)
            const chosen = selectedWindow && time >= selectedWindow.from && time <= selectedWindow.to && selectedCamera === cameraId
            return <button key={alert.id} type="button" className={`hero-ribbon-event severity-${alert.severity} ${chosen ? "is-selected" : ""}`} style={{ left: `${Math.max(1, Math.min(99, (time - from) / RIBBON_DURATION_MS * 100))}%` }} onFocus={() => onHoverCamera(cameraId)} onBlur={() => onHoverCamera(null)} onClick={() => onSelect(alert, { from: Math.max(from, time - EVENT_WINDOW_MS), to: Math.min(now, time + EVENT_WINDOW_MS) })} aria-label={`${cameraId}، ${SEVERITY_LABELS[alert.severity]}، ${formatTime24(time)}. تصفية حسب الكاميرا والوقت`} title={`${cameraId} · ${SEVERITY_LABELS[alert.severity]} · ${formatTime24(time)}`}><span /></button>
          })}
        </div>
      </div>
      })}</div>
      <div className="hero-ribbon-axis" dir="ltr"><bdi className="instrument-num">{formatTime24(from)}</bdi><span>اضغط على إشارة لتصفية الكاميرا والوقت</span><bdi className="instrument-num">{formatTime24(now)}</bdi></div>
      {cameraIds.length > shown.length && <div className="hero-ribbon-more">+{cameraIds.length - shown.length} كاميرات أخرى ضمن التنبيهات المستلمة</div>}
    </> : <div className="hero-ribbon-empty"><span className="hero-ribbon-empty-mark" aria-hidden="true"><i /><i /><i /></span><strong>{isOffline ? "لا تتوفر إشارات من قناة التنبيهات" : "لا تنبيهات مستلمة خلال آخر 30 دقيقة"}</strong><small>{isOffline ? "اتصل بالخادم لعرض أحداث الكاميرات." : "ستظهر مواقع التنبيهات الواردة هنا."}</small></div>}
  </div>
}
