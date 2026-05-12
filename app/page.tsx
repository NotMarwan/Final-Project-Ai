"use client"

import { useState, useEffect, useRef, useCallback, useMemo } from "react"
import dynamic from "next/dynamic"
import { DashboardHeader } from "@/components/dashboard-header"
import { AlertFeed } from "@/components/alert-feed"
import { VideoPlayer } from "@/components/video-player"
import type { LiveAlert } from "@/components/video-player"
import { GeoDashboard } from "@/components/geo-dashboard"

const IncidentPanel = dynamic(() => import("@/components/incident-panel").then(mod => mod.IncidentPanel), { ssr: false })
const AiReport = dynamic(() => import("@/components/ai-report").then(mod => mod.AiReport), { ssr: false })

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const SSE_URL = process.env.NEXT_PUBLIC_SSE_URL ?? `${API_BASE}/alerts`
const FACE_POLICY_REFRESH_MS = 20_000

interface FacePolicyState {
  identityLabelingEnabled: boolean
  recognitionAuditEnabled: boolean
  recognitionAuditCooldownSec: number
  policyUpdatedAt: string | null
}

export default function DashboardPage() {
  const [alerts, setAlerts] = useState<LiveAlert[]>([])
  const [selectedAlert, setSelectedAlert] = useState<LiveAlert | null>(null)
  const [privacyMode, setPrivacyMode] = useState(false)
  const [sseConnected, setSseConnected] = useState(false)
  const [facePolicyFocusSignal, setFacePolicyFocusSignal] = useState(0)
  const [facePolicySynced, setFacePolicySynced] = useState(false)
  const [facePolicyFetchedAt, setFacePolicyFetchedAt] = useState<string | null>(null)
  const [facePolicySyncAgeSec, setFacePolicySyncAgeSec] = useState<number | null>(null)
  const [facePolicy, setFacePolicy] = useState<FacePolicyState>({
    identityLabelingEnabled: true,
    recognitionAuditEnabled: true,
    recognitionAuditCooldownSec: 25,
    policyUpdatedAt: null,
  })
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
        
        // تعيين أحدث تنبيه كتنبيه محدد تلقائياً لتحديث التقرير فوراً
        setSelectedAlert(alertData)
        
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

  const refreshFacePolicy = useCallback(async () => {
    try {
      let policy: Record<string, unknown> = {}
      let fetchedAt = new Date().toISOString()
      const policyRes = await fetch(`${API_BASE}/face/policy`)
      if (policyRes.ok) {
        const payload = await policyRes.json()
        policy = (payload?.policy ?? {}) as Record<string, unknown>
        fetchedAt = typeof payload?.policyFetchedAt === "string" ? payload.policyFetchedAt : fetchedAt
      } else {
        const statusRes = await fetch(`${API_BASE}/face/status`)
        if (!statusRes.ok) throw new Error(`Policy fetch failed: ${statusRes.status}`)
        const payload = await statusRes.json()
        policy = (payload?.policy ?? {}) as Record<string, unknown>
      }

      setFacePolicy((current) => ({
        identityLabelingEnabled:
          typeof policy.identityLabelingEnabled === "boolean"
            ? policy.identityLabelingEnabled
            : current.identityLabelingEnabled,
        recognitionAuditEnabled:
          typeof policy.recognitionAuditEnabled === "boolean"
            ? policy.recognitionAuditEnabled
            : current.recognitionAuditEnabled,
        recognitionAuditCooldownSec:
          typeof policy.recognitionAuditCooldownSec === "number"
            ? policy.recognitionAuditCooldownSec
            : current.recognitionAuditCooldownSec,
        policyUpdatedAt:
          typeof policy.policyUpdatedAt === "string" && policy.policyUpdatedAt.trim().length > 0
            ? policy.policyUpdatedAt
            : current.policyUpdatedAt,
      }))
      setFacePolicyFetchedAt(fetchedAt)
      setFacePolicySynced(true)
    } catch {
      // Keep latest known policy on transient network failures, but flag stale sync state.
      setFacePolicySynced(false)
    }
  }, [])

  useEffect(() => {
    void refreshFacePolicy()
    const timer = setInterval(() => {
      void refreshFacePolicy()
    }, FACE_POLICY_REFRESH_MS)

    return () => {
      clearInterval(timer)
    }
  }, [refreshFacePolicy])

  // View mode: single camera (CAM-01 or CAM-02) or combined side-by-side
  type ViewMode = "CAM-01" | "CAM-02" | "COMBINED"
  const [viewMode, setViewMode] = useState<ViewMode>("CAM-01")

  // Alerts filtered for each camera
  const cam1Alerts = useMemo(() =>
    alerts.filter(a => a.cameraId === "CAM-01"),
    [alerts]
  )
  const cam2Alerts = useMemo(() =>
    alerts.filter(a => a.cameraId === "CAM-02"),
    [alerts]
  )

  // Determine alerts and active alert for video display based on view mode
  const latestAlertForVideo =
    viewMode === "COMBINED"
      ? null // Combined view doesn't show single alert overlay
      : (viewMode === "CAM-01" ? cam1Alerts[0] : cam2Alerts[0]) ?? null

  const handlePrivacyToggle = useCallback((val: boolean) => {
    setPrivacyMode(val)
  }, [])

  const handleFacePolicyClick = useCallback(() => {
    setFacePolicyFocusSignal((prev) => prev + 1)
    void refreshFacePolicy()
  }, [refreshFacePolicy])

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <DashboardHeader 
        privacyMode={privacyMode} 
        onPrivacyToggle={handlePrivacyToggle} 
        sseConnected={sseConnected} 
        totalAlerts={alerts.length} 
        onFacePolicyClick={handleFacePolicyClick}
        facePolicySynced={facePolicySynced}
        facePolicySyncAgeSec={facePolicySyncAgeSec}
        facePolicy={facePolicy}
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
        {/* Area for single-camera view with switcher */}
        <main className="flex-1 overflow-hidden border-r border-border bg-black flex flex-col">
          {/* Camera switcher bar */}
          <div className="flex items-center gap-2 border-b border-border bg-card/80 px-4 py-2">
            <span className="text-xs font-mono text-muted-foreground">View:</span>
            <button
              onClick={() => setDisplayCameraId("CAM-01")}
              className={`px-3 py-1 rounded text-xs font-semibold border transition-colors ${
                displayCameraId === "CAM-01"
                  ? "border-red-500/60 bg-red-500/15 text-red-400"
                  : "border-border bg-secondary text-foreground hover:bg-accent"
              }`}
            >
              CAM-01
            </button>
            <button
              onClick={() => setDisplayCameraId("CAM-02")}
              className={`px-3 py-1 rounded text-xs font-semibold border transition-colors ${
                displayCameraId === "CAM-02"
                  ? "border-red-500/60 bg-red-500/15 text-red-400"
                  : "border-border bg-secondary text-foreground hover:bg-accent"
              }`}
            >
              CAM-02
            </button>
            <span className="ml-auto text-[10px] font-mono text-muted-foreground">
              Both cameras are actively processing
            </span>
          </div>

          {/* Video player */}
          <div className="flex-1">
            <VideoPlayer cameraId={displayCameraId} activeAlert={latestAlertForVideo} privacyMode={privacyMode} />
          </div>
        </main>

        {/* شريط جانبي أيمن: تفاصيل الحادث والتحكم (بدون التقرير) */}
        <aside className="w-[380px] flex-shrink-0 overflow-y-auto custom-scrollbar border-l border-border bg-card/30">
          <div className="flex flex-col gap-3 p-3">
            <GeoDashboard
              alert={selectedAlert ?? latestAlertForVideo}
              alerts={alerts}
              focusCameraId={selectedAlert?.cameraId ?? latestAlertForVideo?.cameraId ?? "CAM-01"}
            />
            <IncidentPanel alert={selectedAlert} focusFacePolicySignal={facePolicyFocusSignal} />
          </div>
        </aside>
      </div>
    </div>
  )
}
