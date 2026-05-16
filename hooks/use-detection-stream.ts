"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import type { DetectionOverlayData } from "@/components/canvas-overlay"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

export function useDetectionStream(cameraId: string) {
  const [data, setData] = useState<DetectionOverlayData | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    const url = `${API_BASE}/detections?camera_id=${encodeURIComponent(cameraId)}`
    const es = new EventSource(url)
    eventSourceRef.current = es

    es.onopen = () => {
      setConnected(true)
      setError(null)
    }

    es.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        const mapped: DetectionOverlayData = {
          tracks: (parsed.tracks || []).map((t: any) => ({
            id: t.id ?? "?",
            bbox: t.bbox ?? [0, 0, 0, 0],
            confidence: t.confidence ?? 0,
            color: t.color ?? [0, 255, 255],
          })),
          personCount: parsed.personCount ?? 0,
          isThreat: parsed.isThreat ?? false,
          threatConfidence: parsed.threatConfidence ?? 0,
          fps: parsed.fps ?? 0,
          weaponScore: parsed.weaponScore ?? 0,
        }
        setData(mapped)
      } catch (err) {
        console.warn("[DetectionStream] Failed to parse SSE data:", err)
      }
    }

    es.onerror = () => {
      setConnected(false)
      setError("Connection lost")
      es.close()
      reconnectTimerRef.current = setTimeout(() => {
        connect()
      }, 2000)
    }
  }, [cameraId])

  useEffect(() => {
    connect()
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
    }
  }, [connect])

  return { data, connected, error }
}