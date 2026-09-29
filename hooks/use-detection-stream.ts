"use client"

import { useEffect, useRef, useState } from "react"
import type { DetectionOverlayData } from "@/components/canvas-overlay"
import { areDetectionOverlayDataEqual, shouldPublishDetectionSnapshot } from "@/lib/live-visual-state"
import { parseDetectionOverlayEnvelope } from "@/lib/detection-envelope"
import { reconnectDelayMs } from "@/lib/reconnect-backoff"
import { applyModalityFreshness, emptyModalityFreshness, parseTelemetry, appendTelemetryPoint, telemetryIsStale, inferenceIsStale, updateModalityFreshness, type ModalityFreshness, type PipelineTelemetry, type TelemetryPoint } from "@/lib/pipeline-telemetry"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const UI_INTERVAL_MS = 1_000

/** The canvas reads overlayRef on each animation frame; React receives only sampled telemetry. */
export function useDetectionStream(cameraId: string) {
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const overlayRef = useRef<DetectionOverlayData | null>(null)
  const telemetryRef = useRef<PipelineTelemetry | null>(null)
  const historyRef = useRef<TelemetryPoint[]>([])
  const receivedAtRef = useRef<number | null>(null)
  const sampleReceivedAtRef = useRef<number | null>(null)
  const modalityFreshnessRef = useRef<ModalityFreshness>(emptyModalityFreshness())
  const lastSequenceRef = useRef<number | null>(null)
  const lastPublishedAtRef = useRef<number | null>(null)
  const lastPublishedDecisionRef = useRef<string | null>(null)

  useEffect(() => {
    let stopped = false
    let source: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    // WT-17 (S-09): reconnect-storm safety — exponential backoff + jitter replaces
    // the fixed 2s retry (agreed with WT-13; hunk limited to reconnect logic).
    let reconnectAttempt = 0
    overlayRef.current = null
    telemetryRef.current = null
    historyRef.current = []
    receivedAtRef.current = null
    sampleReceivedAtRef.current = null
    modalityFreshnessRef.current = emptyModalityFreshness()
    lastSequenceRef.current = null
    lastPublishedAtRef.current = null
    lastPublishedDecisionRef.current = null
    setConnected(false)
    setNow(Date.now())

    const connect = () => {
      if (stopped) return
      source?.close()
      const es = new EventSource(`${API_BASE}/detections?camera_id=${encodeURIComponent(cameraId)}`)
      source = es
      es.onopen = () => { if (source === es) { reconnectAttempt = 0; setConnected(true); setError(null) } }
      es.onmessage = (event) => {
        if (source !== es) return
        try {
          const raw: unknown = JSON.parse(event.data)
          const snapshot = parseTelemetry(raw, cameraId)
          if (!snapshot) return
          const mapped = parseDetectionOverlayEnvelope(raw)
          if (!mapped) throw new Error("Invalid detection payload")
          const received = Date.now()
          if (snapshot.sequence !== null && snapshot.sequence > 0 && snapshot.sequence !== lastSequenceRef.current) {
            lastSequenceRef.current = snapshot.sequence
            sampleReceivedAtRef.current = received
          }
          modalityFreshnessRef.current = updateModalityFreshness(modalityFreshnessRef.current, snapshot, received)
          telemetryRef.current = snapshot
          receivedAtRef.current = received
          historyRef.current = appendTelemetryPoint(historyRef.current, snapshot, received)
          const overlay: DetectionOverlayData = {
            ...mapped,
            videoWidth: mapped.videoWidth ?? 1280,
            videoHeight: mapped.videoHeight ?? 720,
          }
          if (!overlayRef.current || !areDetectionOverlayDataEqual(overlayRef.current, overlay)) overlayRef.current = overlay
          if (shouldPublishDetectionSnapshot(lastPublishedAtRef.current, received, lastPublishedDecisionRef.current, snapshot.decisionState)) {
            lastPublishedAtRef.current = received
            lastPublishedDecisionRef.current = snapshot.decisionState
            setNow(received)
          }
          setError(null)
        } catch {
          setError("Invalid detection data")
          receivedAtRef.current = null
        }
      }
      es.onerror = () => {
        if (source !== es) return
        setConnected(false)
        setError("Connection lost")
        es.close()
        // WT-17 (S-09): exponential backoff + jitter (was fixed 2_000 ms).
        reconnectAttempt += 1
        reconnectTimer = setTimeout(connect, reconnectDelayMs(reconnectAttempt))
      }
    }
    connect()
    const clock = setInterval(() => {
      const tick = Date.now()
      if (lastPublishedAtRef.current === null || tick - lastPublishedAtRef.current >= UI_INTERVAL_MS) {
        lastPublishedAtRef.current = tick
        setNow(tick)
      }
    }, UI_INTERVAL_MS)
    return () => {
      stopped = true
      clearInterval(clock)
      source?.close()
      if (reconnectTimer) clearTimeout(reconnectTimer)
    }
  }, [cameraId])

  const telemetry = telemetryRef.current
  const stale = telemetryIsStale(telemetry, receivedAtRef.current, now)
  const inferenceStale = inferenceIsStale(telemetry?.sequence ?? null, sampleReceivedAtRef.current, now)
  const freshTelemetry = telemetry ? applyModalityFreshness(telemetry, modalityFreshnessRef.current, now) : null
  return { data: connected && !stale && !inferenceStale ? overlayRef.current : null, overlayRef, connected, error, telemetry: freshTelemetry, history: historyRef.current, stale, inferenceStale, now }
}
