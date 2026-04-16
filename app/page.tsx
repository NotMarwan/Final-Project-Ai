"use client"

import { useState, useEffect, useRef, useCallback, useMemo, memo } from "react"
import dynamic from "next/dynamic"
import { DashboardHeader } from "@/components/dashboard-header"
import { AlertFeed } from "@/components/alert-feed"
import { VideoPlayer } from "@/components/video-player"
import type { LiveAlert } from "@/components/video-player"

const IncidentPanel = dynamic(() => import("@/components/incident-panel").then(mod => mod.IncidentPanel), { ssr: false })
const AiReport = dynamic(() => import("@/components/ai-report").then(mod => mod.AiReport), { ssr: false })

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

        // تجاهل تقارير الذكاء الاصطناعي النصية هنا لأنها تُعالج داخل مكون AiReport
        if (data.type === "VLM_Report") return

        const alertData = data as LiveAlert
        setAlerts((prev) => {
          if (prev.some((a) => a.id === alertData.id)) return prev
          return [alertData, ...prev].slice(0, 50)
        })
        
        // تعيين أحدث تنبيه كتنبيه محدد تلقائياً إذا لم يتم تحديد شيء
        setSelectedAlert((current) => current ?? alertData)
        
      } catch (e) {
        // تجاهل أخطاء تحليل البيانات البسيطة
      }
    }

    es.onerror = () => {
      console.error("❌ SSE Error")
      setSseConnected(false)
      es.close()
      // محاولة إعادة الاتصال بعد 3 ثواني
      reconnectTimerRef.current = setTimeout(connectSSE, 3000)
    }
  }, [])

  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    connectSSE()
    return () => {
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
    }
  }, [connectSSE])

  useEffect(() => {
    connectSSE()
    return () => esRef.current?.close()
  }, [connectSSE])

  // التنبيه النشط للفيديو هو أحدث تنبيه تم استقباله
  const latestAlertForVideo = useMemo(() => alerts[0] ?? null, [alerts])

  const handleSelectAlert = useCallback((alert: LiveAlert) => {
    setSelectedAlert(alert)
  }, [])

  const handlePrivacyToggle = useCallback((val: boolean) => {
    setPrivacyMode(val)
  }, [])

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <DashboardHeader 
        privacyMode={privacyMode} 
        onPrivacyToggle={handlePrivacyToggle} 
        sseConnected={sseConnected} 
        totalAlerts={alerts.length} 
      />
      
      <div className="flex flex-1 overflow-hidden">
        {/* شريط جانبي أيسر معاد هيكلته: 50% تنبيهات / 50% تقرير */}
        <aside className="w-[360px] flex-shrink-0 border-r border-border bg-card/30 flex flex-col h-full overflow-hidden">
          {/* النصف العلوي: خلاصة التنبيهات مع سحاب */}
          <div className="h-1/2 border-b border-border flex flex-col overflow-hidden">
            <AlertFeed 
              alerts={alerts} 
              selectedAlertId={selectedAlert?.id ?? null} 
              onSelectAlert={handleSelectAlert} 
            />
          </div>
          
          {/* النصف السفلي: تقرير الذكاء الاصطناعي الجنائي (واسع ومفصل) */}
          <div className="h-1/2 flex flex-col overflow-hidden p-3 bg-background/20">
            <AiReport alertId={selectedAlert?.id} />
          </div>
        </aside>

        {/* المنطقة المركزية: مشغل الفيديو */}
        <main className="flex-1 overflow-hidden border-r border-border bg-black">
          <VideoPlayer activeAlert={latestAlertForVideo} privacyMode={privacyMode} />
        </main>

        {/* شريط جانبي أيمن: تفاصيل الحادث والتحكم (بدون التقرير) */}
        <aside className="w-80 flex-shrink-0 bg-card/30 overflow-y-auto custom-scrollbar">
          <IncidentPanel alert={selectedAlert} />
        </aside>
      </div>
    </div>
  )
}