"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { apiFetch } from "@/lib/api-auth"
import { reconnectDelayMs } from "@/lib/reconnect-backoff"

interface WebRTCPlayerProps {
  streamUrl: string
  camId: string
  onError?: () => void
  onConnected?: () => void
  className?: string
}

const MAX_RETRIES = 3

export function WebRTCPlayer({ streamUrl, onError, onConnected, className = "" }: WebRTCPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const pcRef = useRef<RTCPeerConnection | null>(null)
  const retryCountRef = useRef(0)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState(false)
  const [retrying, setRetrying] = useState(false)

  const cleanup = useCallback(() => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
    if (pcRef.current) {
      pcRef.current.close()
      pcRef.current = null
    }
    setConnected(false)
  }, [])

  const connect = useCallback(() => {
    if (!streamUrl || !videoRef.current) return
    cleanup()

    const pc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    })
    pcRef.current = pc

    const iceCandidates: RTCIceCandidateInit[] = []
    let remoteDescSet = false

    pc.ontrack = (event) => {
      if (videoRef.current && event.streams[0]) {
        videoRef.current.srcObject = event.streams[0]
        setConnected(true)
        setError(false)
        retryCountRef.current = 0
      }
    }

    pc.onicecandidate = (event) => {
      if (event.candidate) {
        if (remoteDescSet) {
          apiFetch(streamUrl, {
            method: "PATCH",
            headers: { "Content-Type": "application/trickle-ice-sdpfrag" },
            body: `a=${event.candidate.candidate}`,
          }).catch(() => {})
        } else {
          iceCandidates.push(event.candidate.toJSON())
        }
      }
    }

    pc.oniceconnectionstatechange = () => {
      const state = pc.iceConnectionState
      if (state === "connected" || state === "completed") {
        setConnected(true)
        setError(false)
        retryCountRef.current = 0
      } else if (state === "failed" || state === "disconnected") {
        if (retryCountRef.current < MAX_RETRIES) {
          retryCountRef.current++
          setRetrying(true)
          retryTimerRef.current = setTimeout(() => {
            setRetrying(false)
            setConnected(false)
            connect()
          }, reconnectDelayMs(retryCountRef.current))
        } else {
          setError(true)
          setConnected(false)
          onError?.()
        }
      }
    }

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "failed") {
        if (retryCountRef.current < MAX_RETRIES) {
          retryCountRef.current++
          setRetrying(true)
          retryTimerRef.current = setTimeout(() => {
            setRetrying(false)
            setConnected(false)
            connect()
          }, reconnectDelayMs(retryCountRef.current))
        } else {
          setError(true)
          onError?.()
        }
      }
    }

    pc.addTransceiver("video", { direction: "recvonly" })
    pc.createOffer()
      .then((offer) => pc.setLocalDescription(offer))
      .then(() => {
        return apiFetch(streamUrl, {
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
          body: pc.localDescription!.sdp,
        })
      })
      .then((res) => {
        if (!res.ok) throw new Error(`WHEP failed: ${res.status}`)
        return res.text()
      })
      .then((sdp) => {
        remoteDescSet = true
        return pc.setRemoteDescription({ type: "answer", sdp })
      })
      .then(() => {
        iceCandidates.forEach((candidate) => {
          pc.addIceCandidate(new RTCIceCandidate(candidate)).catch(() => {})
        })
      })
      .catch(() => {
        console.warn("[WebRTC] Connection failed")
        if (retryCountRef.current < MAX_RETRIES) {
          retryCountRef.current++
          setRetrying(true)
          retryTimerRef.current = setTimeout(() => {
            setRetrying(false)
            setConnected(false)
            connect()
          }, reconnectDelayMs(retryCountRef.current))
        } else {
          setError(true)
          onError?.()
        }
      })
  }, [streamUrl, onError, onConnected, cleanup])

  useEffect(() => {
    connect()
    return cleanup
  }, [connect, cleanup])

  return (
    <div className={`relative bg-[var(--surface-0)] ${className}`}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        onLoadedData={() => onConnected?.()}
        className="h-full w-full object-contain"
      />
      {!connected && !error && !retrying && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="rounded border border-[var(--border-hairline)] bg-[var(--surface-1)]/90 px-3 py-1.5 text-xs text-[var(--text-secondary)]">جارٍ اتصال الفيديو…</span>
        </div>
      )}
      {retrying && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="rounded border border-[var(--state-replay)] bg-[var(--surface-1)]/90 px-3 py-1.5 text-xs text-[var(--state-replay)]">إعادة اتصال الفيديو…</span>
        </div>
      )}
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-[var(--surface-0)]/80">
          <span className="rounded border border-[var(--state-offline)] bg-[var(--surface-1)]/90 px-3 py-1.5 text-xs text-[var(--state-offline)]">البث غير متاح</span>
        </div>
      )}
    </div>
  )
}
