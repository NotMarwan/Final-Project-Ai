"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { DashboardHeader } from "@/components/dashboard-header"
import { AlertFeed } from "@/components/alert-feed"
import { VideoPlayer } from "@/components/video-player"
import { IncidentPanel } from "@/components/incident-panel"
import type { LiveAlert } from "@/components/video-player"

const SSE_URL = "http://localhost:8000/alerts"

export default function DashboardPage() {
  const [alerts, setAlerts] = useState<LiveAlert[]>([])
  const [selectedAlert, setSelectedAlert] = useState<LiveAlert | null>(null)
  const [privacyMode, setPrivacyMode] = useState(false)
  const [sseConnected, setSseConnected] = useState(false)
  const esRef = useRef<EventSource | null>(null)

  const connectSSE = useCallback(() => {
    if (esRef.current) esRef.current.close()

    const es = new EventSource(SSE_URL)
    esRef.current = es

    es.onopen = () => {
      console.log("✅ Connected to Python AI Engine")
      setSseConnected(true)
    }

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        // ── تخطي التقارير الجنائية لمنع انهيار الواجهة ──
        if (data.type === "VLM_Report") return

        const alertData = data as LiveAlert
        setAlerts((prev) => {
          if (prev.some((a) => a.id === alertData.id)) return prev
          return [alertData, ...prev].slice(0, 50)
        })
        setSelectedAlert(alertData)
      } catch (e) {
        // تجاهل الأخطاء البسيطة
      }
    }

    es.onerror = () => {
      setSseConnected(false)
      es.close()
      setTimeout(connectSSE, 3000)
    }
  }, [connectSSE])
    es.onerror = () => {
      console.error("❌ SSE Error")
      setSseConnected(false)
      es.close()
      setTimeout(connectSSE, 3000)
    }
  }, [])

  useEffect(() => {
    connectSSE()
    return () => esRef.current?.close()
  }, [connectSSE])

  const latestAlert = alerts[0] ?? null

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <DashboardHeader privacyMode={privacyMode} onPrivacyToggle={setPrivacyMode} sseConnected={sseConnected} totalAlerts={alerts.length} />
      <div className="flex flex-1 overflow-hidden">
        <aside className="w-72 flex-shrink-0 border-r border-border bg-card/30">
          <AlertFeed alerts={alerts} selectedAlertId={selectedAlert?.id ?? null} onSelectAlert={setSelectedAlert} />
        </aside>
        <main className="flex-1 overflow-hidden">
          <VideoPlayer activeAlert={latestAlert} privacyMode={privacyMode} />
        </main>
        <aside className="w-80 flex-shrink-0 border-l border-border bg-card/30">
          <IncidentPanel alert={selectedAlert} />
        </aside>
      </div>
    </div>
  )
}