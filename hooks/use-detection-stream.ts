"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import type { DetectionOverlayData } from "@/components/canvas-overlay"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

function shallowEqual(a: DetectionOverlayData, b: DetectionOverlayData): boolean {
  if (a.personCount !== b.personCount) return false
  if (a.isThreat !== b.isThreat) return false
  if (a.threatConfidence !== b.threatConfidence) return false
  if (a.fps !== b.fps) return false
  if (a.tracks.length !== b.tracks.length) return false
  for (let i = 0; i < a.tracks.length; i++) {
    const at = a.tracks[i]
    const bt = b.tracks[i]
    if (at.id !== bt.id || at.confidence !== bt.confidence) return false
    if (at.bbox[0] !== bt.bbox[0] || at.bbox[1] !== bt.bbox[1] ||
        at.bbox[2] !== bt.bbox[2] || at.bbox[3] !== bt.bbox[3]) return false
  }
  return true
}

export function useDetectionStream(cameraId: string) {
  const [data, setData] = useState<DetectionOverlayData | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastDataRef = useRef<DetectionOverlayData | null>(null)

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
        if (!lastDataRef.current || !shallowEqual(lastDataRef.current, mapped)) {
          lastDataRef.current = mapped
          setData(mapped)
        }
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