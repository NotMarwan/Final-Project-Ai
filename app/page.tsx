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
import { buildDemoStopPlan } from "@/lib/live-visual-state"
import { cn } from "@/lib/utils"
import { Play, Activity, Wifi, WifiOff, Server, Bell, Clock, Zap } from "lucide-react"
import { CommandPalette } from "@/components/command-palette"
import { AlertToast } from "@/components/alert-toast"
import { OverlaySettingsPanel, loadSettings, type OverlaySettings } from "@/components/overlay-settings"
import { AlertHistory } from "@/components/alert-history"


type Tab = "monitor" | "demo-clips" | "incidents" | "intelligence" | "operations" | "system"

type LiveSourceId = "CAM-01" | "CAM-02"
type DemoSourceId = "EXAMPLE-01" | "EXAMPLE-02" | "EXAMPLE-03"

const LIVE_SOURCE_DEFS: { id: LiveSourceId; label: string }[] = [
  { id: "CAM-01", label: "CAM-01" },
  { id: "CAM-02", label: "CAM-02" },
]

const DEMO_SOURCE_DEFS: { id: DemoSourceId; label: string }[] = [
  { id: "EXAMPLE-01", label: "FIGHT SAMPLE 1" },
  { id: "EXAMPLE-02", label: "FIGHT SAMPLE 2" },
  { id: "EXAMPLE-03", label: "VIOLENCE SAMPLE 3" },
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
export default function DashboardPage() {
  const [alerts, setAlerts] = useState<LiveAlert[]>([])
  const [selectedAlert, setSelectedAlert] = useState<LiveAlert | null>(null)
  const [privacyMode, setPrivacyMode] = useState(false)
  type SseStatus = "online" | "reconnecting" | "offline"
  const [sseStatus, setSseStatus] = useState<SseStatus>("offline")
  const sseGraceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sseConnected = sseStatus === "online"
  const [personCount, setPersonCount] = useState(0)
  const [overlaySettings, setOverlaySettings] = useState<OverlaySettings>(() => loadSettings())
  const [selectedCategories, setSelectedCategories] = useState<DetectionCategory[]>([])
  const [activeTab, setActiveTab] = useState<Tab>("monitor")
  const [selectedLiveSource, setSelectedLiveSource] = useState<LiveSourceId>("CAM-01")
  const [selectedDemoSource, setSelectedDemoSource] = useState<DemoSourceId | null>(null)
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [showOverlaysGlobal, setShowOverlaysGlobal] = useState(true)
  const [toastAlert, setToastAlert] = useState<LiveAlert | null>(null)
  const activeExampleRef = useRef<DemoSourceId | null>(null)
  const esRef = useRef<EventSource | null>(null)

  const connectSSE = useCallback(() => {
    if (esRef.current) esRef.current.close()

    const es = new EventSource(SSE_URL)
    esRef.current = es

    es.onopen = () => {
      console.log("✅ Connected to Python AI Engine")
      if (sseGraceTimerRef.current) clearTimeout(sseGraceTimerRef.current)
      setSseStatus("online")
    }

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        // تجاهل تقارير الذكاء الاصطناعي النصية هنا لأنها تُعالج داخل مكون AiReport
        if (data.type === "VLM_Report") return

        // Handle person detection metadata
        if (data.type === "person_detection") {
          if (typeof data.personCount === "number") {
            setPersonCount(data.personCount)
          }
          return
        }

        const alertData = data as LiveAlert
        setAlerts((prev) => {
          if (prev.some((a) => a.id === alertData.id)) return prev
          return [alertData, ...prev].slice(0, 50)
        })
        
        // تعيين أحدث تنبيه كتنبيه محدد تلقائياً لتحديث التقرير فوراً
        setSelectedAlert(alertData)
        
      } catch {
        // تجاهل أخطاء تحليل البيانات البسيطة
      }
    }

    es.onerror = () => {
      console.error("❌ SSE Error")
      setSseStatus("reconnecting")
      es.close()
      // 2s grace before showing OFFLINE — short blips stay amber, not red
      sseGraceTimerRef.current = setTimeout(() => setSseStatus("offline"), 2000)
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
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      if (sseGraceTimerRef.current) clearTimeout(sseGraceTimerRef.current)
    }
  }, [connectSSE])

  // Keyboard shortcuts for tabs (1-6) and command palette (Cmd+K / Ctrl+K)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setCommandPaletteOpen((o) => !o)
        return
      }
      if (commandPaletteOpen) return
      if (e.altKey || e.ctrlKey || e.metaKey) return
      const num = Number(e.key)
      if (num >= 1 && num <= 6) {
        setActiveTab(TAB_DEFS[num - 1].id)
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [commandPaletteOpen])

  // Trigger toast when new alert arrives unless the operator is already on incidents
  const prevAlertCountRef = useRef(0)
  useEffect(() => {
    if (alerts.length > prevAlertCountRef.current) {
      const latest = alerts[0]
      if (latest && activeTab !== "incidents") {
        setToastAlert(latest)
      }
    }
    prevAlertCountRef.current = alerts.length
  }, [alerts.length, activeTab])

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

  const cleanupTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const stopDemoSource = useCallback(async (id: DemoSourceId) => {
    try {
      await fetch(`${API_BASE}/demo_stop/${id}`, { method: "DELETE" })
    } catch { /* ignore — backend may already have stopped */ }
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
    const stopPlan = activeTab !== "demo-clips"
      ? buildDemoStopPlan(activeExampleRef.current)
      : null

    if (stopPlan) {
      activeExampleRef.current = null
      void stopDemoSource(stopPlan.immediateStopId)
      cleanupTimerRef.current = setTimeout(() => {
        void stopDemoSource(stopPlan.retryStopId)
      }, 500)
    }
    return () => {
      if (cleanupTimerRef.current) {
        clearTimeout(cleanupTimerRef.current)
        cleanupTimerRef.current = null
      }
    }
  }, [activeTab, stopDemoSource])

  // Stop example worker on page unmount
  useEffect(() => {
    return () => {
      if (activeExampleRef.current) {
        void stopDemoSource(activeExampleRef.current)
      }
      if (cleanupTimerRef.current) {
        clearTimeout(cleanupTimerRef.current)
        cleanupTimerRef.current = null
      }
    }
  }, [stopDemoSource])

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground bg-gradient-animated bg-grid-pattern">
      <DashboardHeader
        privacyMode={privacyMode}
        onPrivacyToggle={handlePrivacyToggle}
        sseConnected={sseConnected}
        totalAlerts={alerts.length}
      />

      <CommandPalette
        open={commandPaletteOpen}
        onOpenChange={setCommandPaletteOpen}
        onTabChange={setActiveTab}
        onToggleOverlays={() => setShowOverlaysGlobal((v) => !v)}
        overlaysOn={showOverlaysGlobal}
        onTogglePrivacy={() => setPrivacyMode((v) => !v)}
        privacyOn={privacyMode}
        alerts={alerts}
        onSelectAlert={handleSelectAlert}
        activeTab={activeTab}
      />

      <AlertToast
        alert={toastAlert}
        activeTab={activeTab}
        onNavigate={() => {
          setActiveTab("incidents")
          if (toastAlert) setSelectedAlert(toastAlert)
          setToastAlert(null)
        }}
        onDismiss={() => setToastAlert(null)}
      />

      {/* ── Mission Control Tab Strip ── */}
      <nav role="tablist" aria-label="Dashboard sections" className="flex shrink-0 flex-nowrap border-b border-border/40 bg-card/30 px-3 md:px-4 relative overflow-x-auto backdrop-blur-sm">
        {/* Ambient glow line */}
        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary/20 to-transparent" />

        {TAB_DEFS.map(({ id, label }, idx) => {
          const isActive = activeTab === id
          const hasMonitorGlow = id === "monitor" && sseConnected
          const hasAlertGlow = id === "incidents" && alerts.length > 0
          return (
            <button
              key={id}
              role="tab"
              aria-selected={isActive}
              aria-controls={`panel-${id}`}
              id={`tab-${id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => setActiveTab(id)}
              className={cn(
                "group relative inline-flex items-center gap-1.5 md:gap-2 px-2.5 md:px-4 py-2.5 text-xs md:text-sm font-semibold transition-all duration-200 outline-none focus-visible:ring-2 focus-visible:ring-primary/40 rounded-md my-1",
                isActive
                  ? "text-primary bg-primary/10"
                  : "text-muted-foreground hover:text-foreground hover:bg-white/[0.03]"
              )}
            >
              {/* Active indicator pill */}
              {isActive && (
                <span className="absolute inset-x-1 -bottom-1 h-0.5 rounded-full bg-primary shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
              )}

              {/* Status dot */}
              {hasMonitorGlow && (
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ambient-pulse rounded-full bg-success opacity-80" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-success glow-success" />
                </span>
              )}
              {hasAlertGlow && (
                <span className="relative flex h-1.5 w-1.5">
                  <span className="absolute inline-flex h-full w-full animate-ambient-pulse rounded-full bg-danger opacity-80" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-danger glow-danger" />
                </span>
              )}

              <span className="truncate">{label}</span>

              {/* Alert count badge */}
              {id === "incidents" && alerts.length > 0 && (
                <span className="ml-0.5 rounded-full bg-destructive/90 px-1.5 py-0 text-[10px] font-bold leading-none text-destructive-foreground animate-threat-flash">
                  {alerts.length > 99 ? "99+" : alerts.length}
                </span>
              )}

              {/* Keyboard shortcut hint */}
              <span className={cn(
                "hidden lg:inline-flex ml-0.5 rounded px-1 py-[1px] text-[10px] font-mono border transition-colors",
                isActive
                  ? "border-primary/30 text-primary/70 bg-primary/5"
                  : "border-transparent text-muted-foreground/30 group-hover:border-white/5 group-hover:text-muted-foreground/40"
              )}>
                {idx + 1}
              </span>
            </button>
          )
        })}
      </nav>

      {/* Tab content */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Live Monitor ── */}
        {activeTab === "monitor" && (
          <div id="panel-monitor" role="tabpanel" aria-labelledby="tab-monitor" className="flex flex-1 overflow-hidden">
            <aside className="hidden md:flex flex-col h-full w-[300px] flex-shrink-0 overflow-hidden border-r border-border bg-card/30">
              <div className="flex-1 overflow-hidden">
                <AlertFeed
                  alerts={filteredAlerts}
                  selectedAlertId={selectedAlert?.id ?? null}
                  onSelectAlert={handleSelectAlert}
                  selectedCategories={selectedCategories}
                  onCategoryChange={setSelectedCategories}
                  categoryCounts={categoryCounts}
                />
              </div>
              <div className="border-t border-border/60 h-[200px] flex-shrink-0 overflow-hidden">
                <AlertHistory
                  alerts={alerts}
                  selectedAlertId={selectedAlert?.id ?? null}
                  onSelectAlert={handleSelectAlert}
                />
              </div>
            </aside>
            <main className="flex-1 flex flex-col overflow-hidden bg-black">
              {/* Live source switcher — live cameras only */}
              <div className="flex shrink-0 items-center gap-2 border-b border-border bg-card/80 px-3 py-2">
                <span className="font-mono text-[10px] font-bold text-red-400 mr-1 tracking-widest uppercase">LIVE CAMERAS</span>
                {LIVE_SOURCE_DEFS.map(({ id, label }) => (
                  <button
                    key={id}
                    onClick={() => setSelectedLiveSource(id)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 min-h-[44px] text-xs font-semibold transition-colors ${
                      selectedLiveSource === id
                        ? "border-red-500 bg-red-500/20 text-red-400"
                        : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground"
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${selectedLiveSource === id ? "bg-red-500 animate-pulse" : "bg-muted-foreground/40"}`} />
                    {label}
                    <span className="rounded px-1 py-0.5 text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">LIVE</span>
                  </button>
                ))}
                <span className="ml-auto font-mono text-[9px] text-muted-foreground/60">
                  Live monitoring sources: CAM-01 + CAM-02
                </span>
                <OverlaySettingsPanel
                  settings={overlaySettings}
                  onChange={(s) => {
                    setOverlaySettings(s)
                    try { localStorage.setItem("ai-sentinel-overlay-settings", JSON.stringify(s)) } catch { /* ignore */ }
                  }}
                />
              </div>
              <div className="flex-1 overflow-hidden">
                <VideoPlayer cameraId={selectedLiveSource} activeAlert={latestAlertForVideo} privacyMode={privacyMode} personCount={personCount} overlaySettings={overlaySettings} />
              </div>
              </main>
            </div>
          )}

          {/* ── Demo Clips ── */}
          {activeTab === "demo-clips" && (
          <div id="panel-demo-clips" role="tabpanel" aria-labelledby="tab-demo-clips" className="flex flex-1 overflow-hidden">
            <aside className="hidden md:block flex h-full w-[300px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-card/30">
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
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 min-h-[44px] text-xs font-semibold transition-colors ${
                      selectedDemoSource === id
                        ? "border-amber-500 bg-amber-500/20 text-amber-400"
                        : "border-border text-muted-foreground hover:border-primary/50 hover:text-foreground"
                    }`}
                  >
                    <span className={`h-1.5 w-1.5 rounded-full ${selectedDemoSource === id ? "bg-amber-400" : "bg-muted-foreground/40"}`} />
                    {label}
                    <span className="rounded px-1 py-0.5 text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">DEMO</span>
                  </button>
                ))}
                <span className="ml-auto font-mono text-[9px] text-muted-foreground/60">
                  Demo clips are analyzed only when selected
                </span>
                <OverlaySettingsPanel
                  settings={overlaySettings}
                  onChange={(s) => {
                    setOverlaySettings(s)
                    try { localStorage.setItem("ai-sentinel-overlay-settings", JSON.stringify(s)) } catch { /* ignore */ }
                  }}
                />
              </div>
              <div className="flex-1 overflow-hidden">
                {selectedDemoSource ? (
                  <VideoPlayer cameraId={selectedDemoSource} activeAlert={latestAlertForVideo} privacyMode={privacyMode} personCount={personCount} overlaySettings={overlaySettings} />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
                    <Play className="h-8 w-8 text-muted-foreground/20" />
                    <p className="font-mono text-sm font-semibold text-muted-foreground">No demo clip selected</p>
                    <p className="font-mono text-[11px] text-muted-foreground/60">Select an EXAMPLE above to begin demo analysis</p>
                  </div>
                )}
              </div>
            </main>
          </div>
        )}

        {/* ── Incidents ── */}
        {activeTab === "incidents" && (
          <div id="panel-incidents" role="tabpanel" aria-labelledby="tab-incidents" className="flex flex-1 overflow-hidden">
            <aside className="hidden md:block flex h-full w-[320px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-card/30">
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
                <IncidentPanel alert={selectedAlert} />
              </div>
            </main>
            <aside className="hidden md:block flex h-full w-[400px] flex-shrink-0 flex-col overflow-hidden border-l border-border bg-card/30">
              <ClipSidebar
                alerts={alerts}
                selectedAlertId={selectedAlert?.id}
                onSelectAlert={handleSelectAlert}
              />
            </aside>
          </div>
        )}

        {/* ── Intelligence ── */}
        {activeTab === "intelligence" && (
          <div id="panel-intelligence" role="tabpanel" aria-labelledby="tab-intelligence" className="flex flex-1 overflow-hidden">
            <aside className="hidden md:block flex h-full w-[280px] flex-shrink-0 flex-col overflow-hidden border-r border-border bg-card/30">
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
          </div>
        )}

        {/* ── Operations ── */}
        {activeTab === "operations" && (
          <div id="panel-operations" role="tabpanel" aria-labelledby="tab-operations" className="flex flex-1 overflow-hidden">
            <main className="flex-1 overflow-y-auto p-4">
              <GeoDashboard
                alert={selectedAlert ?? latestAlertForVideo}
                alerts={alerts}
                focusCameraId={selectedAlert?.cameraId ?? latestAlertForVideo?.cameraId ?? "CAM-01"}
              />
            </main>
            <aside className="hidden md:block w-[320px] flex-shrink-0 overflow-y-auto border-l border-border bg-card/30 p-3">
              <TelegramStatusCard />
            </aside>
          </div>
        )}

        {/* ── System ── */}
        {activeTab === "system" && (
          <div id="panel-system" role="tabpanel" aria-labelledby="tab-system" className="flex flex-1 overflow-hidden">
            <main className="flex-1 overflow-y-auto p-4 md:p-6">
            <div className="mx-auto max-w-4xl space-y-4">
              {/* Header */}
              <div className="flex items-center gap-2 mb-4">
                <Server className="h-4 w-4 text-primary" />
                <h2 className="text-sm font-bold tracking-tight uppercase">System Status</h2>
              </div>

              {/* Status cards grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                {/* SSE Status */}
                <div className="rounded-lg border border-border/60 bg-card/60 p-3 relative overflow-hidden">
                  <div className="absolute inset-0 bg-dot-grid opacity-20 pointer-events-none" />
                  <div className="relative flex items-center justify-between mb-2">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">SSE Link</span>
                    {sseStatus === "online" ? (
                      <Wifi className="h-3.5 w-3.5 text-success" />
                    ) : sseStatus === "reconnecting" ? (
                      <Wifi className="h-3.5 w-3.5 text-amber-400" />
                    ) : (
                      <WifiOff className="h-3.5 w-3.5 text-danger" />
                    )}
                  </div>
                  <div className="relative flex items-center gap-2">
                    <span className={cn(
                      "h-2 w-2 rounded-full",
                      sseStatus === "online" ? "bg-success animate-ambient-pulse"
                      : sseStatus === "reconnecting" ? "bg-amber-400 animate-pulse"
                      : "bg-danger"
                    )} />
                    <span className={cn(
                      "text-xs font-bold",
                      sseStatus === "online" ? "text-success"
                      : sseStatus === "reconnecting" ? "text-amber-400"
                      : "text-danger"
                    )}>
                      {sseStatus === "online" ? "ONLINE"
                      : sseStatus === "reconnecting" ? "RECONNECTING…"
                      : "OFFLINE"}
                    </span>
                  </div>
                  <p className="relative text-[9px] text-muted-foreground/60 font-mono mt-1 truncate">{SSE_URL}</p>
                </div>

                {/* Alerts Counter */}
                <div className="rounded-lg border border-border/60 bg-card/60 p-3 relative overflow-hidden">
                  <div className="absolute inset-0 bg-dot-grid opacity-20 pointer-events-none" />
                  <div className="relative flex items-center justify-between mb-2">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Alerts</span>
                    <Bell className="h-3.5 w-3.5 text-warning" />
                  </div>
                  <div className="relative text-xl font-black font-mono text-foreground">
                    {alerts.length}
                  </div>
                  <p className="relative text-[9px] text-muted-foreground/60 mt-1">This session</p>
                </div>

                {/* System Time */}
                <div className="rounded-lg border border-border/60 bg-card/60 p-3 relative overflow-hidden">
                  <div className="absolute inset-0 bg-dot-grid opacity-20 pointer-events-none" />
                  <div className="relative flex items-center justify-between mb-2">
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Uptime</span>
                    <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                  </div>
                  <div className="relative text-xl font-black font-mono text-foreground">
                    {Math.floor(alerts.length > 0 ? alerts.length * 0.5 : 0)}m
                  </div>
                  <p className="relative text-[9px] text-muted-foreground/60 mt-1">Estimated session</p>
                </div>
              </div>

              {/* Detailed status bars */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {/* Connection health */}
                <div className="rounded-lg border border-border/60 bg-card/60 p-4 relative overflow-hidden">
                  <div className="absolute inset-0 bg-dot-grid opacity-20 pointer-events-none" />
                  <div className="relative flex items-center gap-2 mb-3">
                    <Activity className="h-4 w-4 text-primary" />
                    <span className="text-xs font-bold">Connection Health</span>
                  </div>
                  <div className="relative space-y-3">
                    <div>
                      <div className="flex justify-between text-[10px] text-muted-foreground mb-1">
                        <span>SSE Stability</span>
                        <span className={sseStatus === "online" ? "text-success" : sseStatus === "reconnecting" ? "text-amber-400" : "text-danger"}>
                          {sseStatus === "online" ? "100%" : sseStatus === "reconnecting" ? "~%" : "0%"}
                        </span>
                      </div>
                      <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                        <div className={cn("h-full rounded-full transition-all duration-500",
                          sseStatus === "online" ? "bg-success" : sseStatus === "reconnecting" ? "bg-amber-400" : "bg-danger"
                        )} style={{ width: sseStatus === "online" ? "100%" : sseStatus === "reconnecting" ? "60%" : "0%" }} />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Alert breakdown */}
                <div className="rounded-lg border border-border/60 bg-card/60 p-4 relative overflow-hidden">
                  <div className="absolute inset-0 bg-dot-grid opacity-20 pointer-events-none" />
                  <div className="relative flex items-center gap-2 mb-3">
                    <Zap className="h-4 w-4 text-warning" />
                    <span className="text-xs font-bold">Alert Breakdown</span>
                  </div>
                  <div className="relative space-y-2">
                    {["critical", "high", "medium"].map((sev) => {
                      const count = alerts.filter((a) => a.severity === sev).length
                      const pct = alerts.length > 0 ? (count / alerts.length) * 100 : 0
                      const color = sev === "critical" ? "bg-danger" : sev === "high" ? "bg-warning" : "bg-primary"
                      return (
                        <div key={sev}>
                          <div className="flex justify-between text-[10px] text-muted-foreground mb-1 capitalize">
                            <span>{sev}</span>
                            <span>{count}</span>
                          </div>
                          <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                            <div className={cn("h-full rounded-full transition-all duration-500", color)} style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>

              <TelegramStatusCard />
            </div>
          </main>
          </div>
        )}

      </div>
    </div>
  )
}
