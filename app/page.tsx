"use client"

import { useState, useEffect, useRef, useCallback, useMemo } from "react"
import dynamic from "next/dynamic"
import { DashboardHeader } from "@/components/dashboard-header"
import { AlertFeed } from "@/components/alert-feed"
import { VideoPlayer } from "@/components/video-player"
import type { LiveAlert } from "@/components/video-player"
import { GeoDashboard } from "@/components/geo-dashboard"
import { ClipSidebar } from "@/components/clip-sidebar"
import { TelegramStatusCard } from "@/components/telegram-status"
import type { DetectionCategory } from "@/lib/detection-types"

type Tab = "monitor" | "demo-clips" | "incidents" | "intelligence" | "operations" | "system"

type LiveSourceId = "CAM-01" | "CAM-02"
type DemoSourceId = "EXAMPLE-01" | "EXAMPLE-02"

const LIVE_SOURCE_DEFS: { id: LiveSourceId; label: string }[] = [
  { id: "CAM-01", label: "CAM-01" },
  { id: "CAM-02", label: "CAM-02" },
]

const DEMO_SOURCE_DEFS: { id: DemoSourceId; label: string }[] = [
  { id: "EXAMPLE-01", label: "EXAMPLE-01" },
  { id: "EXAMPLE-02", label: "EXAMPLE-02" },
]

const TAB_DEFS: { id: Tab; label: string }[] = [
  { id: "monitor",      label: "Live Monitor" },
  { id: "demo-clips",   label: "Demo Clips" },
  { id: "incidents",    label: "Incidents" },
  { id: "intelligence", label: "Intelligence" },
  { id: "operations",   label: "Operations" },
  { id: "system",       label: "System" },
]

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
  const [selectedCategories, setSelectedCategories] = useState<DetectionCategory[]>([])
  const [activeTab, setActiveTab] = useState<Tab>("monitor")
  const [selectedLiveSource, setSelectedLiveSource] = useState<LiveSourceId>("CAM-01")
  const [selectedDemoSource, setSelectedDemoSource] = useState<DemoSourceId | null>(null)
  const activeExampleRef = useRef<DemoSourceId | null>(null)
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

  useEffect(() => {
    if (!facePolicyFetchedAt) {
      setFacePolicySyncAgeSec(null)
      return
    }

    const updateAge = () => {
      const parsed = Date.parse(facePolicyFetchedAt)
      if (Number.isNaN(parsed)) {
        setFacePolicySyncAgeSec(null)
        return
      }
      const ageSec = Math.max(0, Math.floor((Date.now() - parsed) / 1000))
      setFacePolicySyncAgeSec(ageSec)
    }

    updateAge()
    const timer = setInterval(updateAge, 1000)
    return () => clearInterval(timer)
  }, [facePolicyFetchedAt])

  // التنبيه النشط للفيديو هو أحدث تنبيه تم استقباله
  const latestAlertForVideo = useMemo(() => alerts[0] ?? null, [alerts])

  const filteredAlerts = useMemo(() => {
    if (selectedCategories.length === 0) return alerts
    return alerts.filter(a => selectedCategories.includes(a.type.toLowerCase() as DetectionCategory))
  }, [alerts, selectedCategories])

  const categoryCounts = useMemo(() => {
    const counts: Partial<Record<DetectionCategory, number>> = {}
    alerts.forEach(a => {
      const cat = a.type.toLowerCase() as DetectionCategory
      counts[cat] = (counts[cat] || 0) + 1
    })
    return counts
  }, [alerts])

  const handleSelectAlert = useCallback((alert: LiveAlert) => {
    setSelectedAlert(alert)
  }, [])

  const handlePrivacyToggle = useCallback((val: boolean) => {
    setPrivacyMode(val)
  }, [])

  const handleFacePolicyClick = useCallback(() => {
    setFacePolicyFocusSignal((prev) => prev + 1)
    void refreshFacePolicy()
  }, [refreshFacePolicy])

  const stopDemoSource = useCallback(async (id: DemoSourceId) => {
    try {
      await fetch(`${API_BASE}/demo_stop/${id}`, { method: "DELETE" })
    } catch { /* ignore — backend may already have stopped */ }
    activeExampleRef.current = null
  }, [])

  const handleDemoSelect = useCallback(async (id: DemoSourceId) => {
    if (activeExampleRef.current && activeExampleRef.current !== id) {
      await stopDemoSource(activeExampleRef.current)
    }
    setSelectedDemoSource(id)
    activeExampleRef.current = id
    try {
      await fetch(`${API_BASE}/demo_start/${id}`, { method: "POST" })
    } catch { /* backend offline — video will show error state */ }
  }, [stopDemoSource])

  // Stop example worker when leaving Demo Clips tab
  useEffect(() => {
    if (activeTab !== "demo-clips" && activeExampleRef.current) {
      void stopDemoSource(activeExampleRef.current)
    }
  }, [activeTab, stopDemoSource])

  // Stop example worker on page unmount
  useEffect(() => {
    return () => {
      if (activeExampleRef.current) {
        void stopDemoSource(activeExampleRef.current)
      }
    }
  }, [stopDemoSource])

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

      {/* Tab nav */}
      <nav className="flex shrink-0 border-b border-border bg-card/40 px-4">
        {TAB_DEFS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`-mb-px inline-flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {id === "monitor" && sseConnected && (
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-500 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
              </span>
            )}
            {label}
            {id === "incidents" && alerts.length > 0 && (
              <span className="rounded-full bg-destructive px-1.5 py-0.5 text-[10px] font-semibold leading-none text-destructive-foreground">
                {alerts.length > 99 ? "99+" : alerts.length}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* Tab content */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Live Monitor ── */}
        {activeTab === "monitor" && (
          <>
            <aside className="flex h-full w-[300px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-card/30">
              <AlertFeed
                alerts={filteredAlerts}
                selectedAlertId={selectedAlert?.id ?? null}
                onSelectAlert={handleSelectAlert}
                selectedCategories={selectedCategories}
                onCategoryChange={setSelectedCategories}
                categoryCounts={categoryCounts}
              />
            </aside>
            <main className="flex-1 flex flex-col overflow-hidden bg-black">
              {/* Live source switcher — live cameras only */}
              <div className="flex shrink-0 items-center gap-2 border-b border-border bg-card/80 px-3 py-2">
                <span className="font-mono text-[10px] font-bold text-red-400 mr-1 tracking-widest uppercase">LIVE CAMERAS</span>
                {LIVE_SOURCE_DEFS.map(({ id, label }) => (
                  <button
                    key={id}
                    onClick={() => setSelectedLiveSource(id)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold transition-colors ${
                      selectedLiveSource === id
                        ? "border-red-500 bg-red-500/20 text-red-400"
                        : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground"
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${selectedLiveSource === id ? "bg-red-500 animate-pulse" : "bg-muted-foreground/40"}`} />
                    {label}
                    <span className="rounded px-1 py-0.5 text-[9px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">LIVE</span>
                  </button>
                ))}
                <span className="ml-auto font-mono text-[9px] text-muted-foreground/60">
                  Live monitoring sources: CAM-01 + CAM-02
                </span>
              </div>
              <div className="flex-1 overflow-hidden">
                <VideoPlayer cameraId={selectedLiveSource} activeAlert={latestAlertForVideo} privacyMode={privacyMode} />
              </div>
            </main>
          </>
        )}

        {/* ── Demo Clips ── */}
        {activeTab === "demo-clips" && (
          <>
            <aside className="flex h-full w-[300px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-card/30">
              <AlertFeed
                alerts={filteredAlerts}
                selectedAlertId={selectedAlert?.id ?? null}
                onSelectAlert={handleSelectAlert}
                selectedCategories={selectedCategories}
                onCategoryChange={setSelectedCategories}
                categoryCounts={categoryCounts}
              />
            </aside>
            <main className="flex-1 flex flex-col overflow-hidden bg-black">
              {/* Demo source selector */}
              <div className="flex shrink-0 items-center gap-2 border-b border-border bg-card/80 px-3 py-2">
                <span className="font-mono text-[10px] font-bold text-amber-400 mr-1 tracking-widest uppercase">DEMO CLIPS</span>
                {DEMO_SOURCE_DEFS.map(({ id, label }) => (
                  <button
                    key={id}
                    onClick={() => void handleDemoSelect(id)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold transition-colors ${
                      selectedDemoSource === id
                        ? "border-amber-500 bg-amber-500/20 text-amber-400"
                        : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground"
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${selectedDemoSource === id ? "bg-amber-400" : "bg-muted-foreground/40"}`} />
                    {label}
                    <span className="rounded px-1 py-0.5 text-[9px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">DEMO</span>
                  </button>
                ))}
                <span className="ml-auto font-mono text-[9px] text-muted-foreground/60">
                  Demo clips are analyzed only when selected
                </span>
              </div>
              <div className="flex-1 overflow-hidden">
                {selectedDemoSource ? (
                  <VideoPlayer cameraId={selectedDemoSource} activeAlert={latestAlertForVideo} privacyMode={privacyMode} />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
                    <span className="font-mono text-3xl text-muted-foreground/20">▶</span>
                    <p className="font-mono text-sm font-semibold text-muted-foreground">No demo clip selected</p>
                    <p className="font-mono text-[11px] text-muted-foreground/60">Select EXAMPLE-01 or EXAMPLE-02 above to begin demo analysis</p>
                  </div>
                )}
              </div>
            </main>
          </>
        )}

        {/* ── Incidents ── */}
        {activeTab === "incidents" && (
          <>
            <aside className="flex h-full w-[320px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-card/30">
              <AlertFeed
                alerts={filteredAlerts}
                selectedAlertId={selectedAlert?.id ?? null}
                onSelectAlert={handleSelectAlert}
                selectedCategories={selectedCategories}
                onCategoryChange={setSelectedCategories}
                categoryCounts={categoryCounts}
              />
            </aside>
            <main className="flex-1 overflow-y-auto border-r border-border bg-card/30">
              <div className="p-3">
                <IncidentPanel alert={selectedAlert} focusFacePolicySignal={facePolicyFocusSignal} />
              </div>
            </main>
            <aside className="flex h-full w-[400px] flex-shrink-0 flex-col overflow-hidden border-l border-border bg-card/30">
              <ClipSidebar
                alerts={alerts}
                selectedAlertId={selectedAlert?.id}
                onSelectAlert={handleSelectAlert}
              />
            </aside>
          </>
        )}

        {/* ── Intelligence ── */}
        {activeTab === "intelligence" && (
          <>
            <aside className="flex h-full w-[280px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-card/30">
              <AlertFeed
                alerts={filteredAlerts}
                selectedAlertId={selectedAlert?.id ?? null}
                onSelectAlert={handleSelectAlert}
                selectedCategories={selectedCategories}
                onCategoryChange={setSelectedCategories}
                categoryCounts={categoryCounts}
              />
            </aside>
            <main className="flex-1 overflow-y-auto bg-background/20 p-4">
              <AiReport alertId={selectedAlert?.id} />
            </main>
          </>
        )}

        {/* ── Operations ── */}
        {activeTab === "operations" && (
          <>
            <main className="flex-1 overflow-y-auto p-4">
              <GeoDashboard
                alert={selectedAlert ?? latestAlertForVideo}
                alerts={alerts}
                focusCameraId={selectedAlert?.cameraId ?? latestAlertForVideo?.cameraId ?? "CAM-01"}
              />
            </main>
            <aside className="w-[320px] flex-shrink-0 overflow-y-auto border-l border-border bg-card/30 p-3">
              <TelegramStatusCard />
            </aside>
          </>
        )}

        {/* ── System ── */}
        {activeTab === "system" && (
          <main className="flex-1 overflow-y-auto p-6">
            <div className="mx-auto max-w-2xl space-y-4">
              <div className="rounded-lg border border-border bg-card p-4 space-y-2">
                <h2 className="text-sm font-semibold text-foreground">Backend Connection</h2>
                <p className="text-xs text-muted-foreground">
                  SSE:{" "}
                  <span className={sseConnected ? "text-green-500" : "text-red-500"}>
                    {sseConnected ? "Connected" : "Disconnected"}
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">Endpoint: {SSE_URL}</p>
                <p className="text-xs text-muted-foreground">
                  Face Policy Sync:{" "}
                  {facePolicySynced ? `${facePolicySyncAgeSec ?? 0}s ago` : "Stale / unreachable"}
                </p>
                <p className="text-xs text-muted-foreground">
                  Total alerts received: {alerts.length}
                </p>
              </div>
              <TelegramStatusCard />
            </div>
          </main>
        )}

      </div>
    </div>
  )
}
