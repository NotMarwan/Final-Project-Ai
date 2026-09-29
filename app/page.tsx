"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import dynamic from "next/dynamic"
import { AlertToast } from "@/components/alert-toast"
import { loadSettings, type OverlaySettings } from "@/components/overlay-settings"
import { UiMonitorSection, type DemoSourceId, type LiveSourceId } from "@/components/sections/ui-monitor-section"
import type { LiveAlert } from "@/components/video-player"
import type { DetectionCategory } from "@/lib/detection-types"
import { apiFetch } from "@/lib/api-auth"
import { buildDemoStopPlan } from "@/lib/live-visual-state"
import { selectThreatLevel, selectVisibleAlerts } from "@/lib/sentinel-selectors"
import { SentinelProvider, useSentinel } from "@/lib/sentinel-store"
import { useApiAccess } from "@/hooks/use-api-access"
import { AppShell, SECTIONS, type Section } from "@/components/shell/app-shell"
import { CommandPalette } from "@/components/shell/command-palette"
import { Overview } from "@/components/overview/overview"
import { IncidentsSection } from "@/components/sections/incidents-section"

const IncidentPanel = dynamic(() => import("@/components/incident-panel").then((module) => module.IncidentPanel), { ssr: false })
const AlertFeed = dynamic(() => import("@/components/alert-feed").then((module) => module.AlertFeed), { ssr: false })
const ClipSidebar = dynamic(() => import("@/components/clip-sidebar").then((module) => module.ClipSidebar), { ssr: false })
const UiIntelOpsSection = dynamic(() => import("@/components/sections/ui-intel-ops-section").then((module) => module.UiIntelOpsSection), { ssr: false })
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const MAX_TOASTS = 4
const ALERT_ID_DEEP_LINK = /^[A-Za-z0-9_-]{1,128}$/

/** WT-25 (flagged hunk): minimal deep link — `?section=<id>&id=<alertId>`
 *  restores a section and opens one incident; unknown values are ignored and
 *  `?fixtures=1` is preserved. */
function readDeepLink(): { section: Section | null; alertId: string | null } {
  if (typeof window === "undefined") return { section: null, alertId: null }
  const params = new URLSearchParams(window.location.search)
  const requested = params.get("section")
  const section = SECTIONS.some((entry) => entry.id === requested) ? requested as Section : null
  const alertId = params.get("id")
  return { section, alertId: alertId && ALERT_ID_DEEP_LINK.test(alertId) ? alertId : null }
}

function Dashboard() {
  const { alerts, selectedAlert, selectAlert, connectionStatus, personCount, filters, setFilters, fixtureMode, lastRealAlert } = useSentinel()
  const { role: accessRole } = useApiAccess()
  const [section, setSection] = useState<Section>("overview")
  const [collapsed, setCollapsed] = useState(false)
  const [privacyMode, setPrivacyMode] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [overlaySettings, setOverlaySettings] = useState<OverlaySettings>(() => loadSettings())
  const [liveSource, setLiveSource] = useState<LiveSourceId>("CAM-01")
  const [demoSource, setDemoSource] = useState<DemoSourceId | null>(null)
  const [toastQueue, setToastQueue] = useState<LiveAlert[]>([])
  const activeDemoRef = useRef<DemoSourceId | null>(null)
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastToastId = useRef<string | null>(null)
  const visibleAlerts = useMemo(() => selectVisibleAlerts(alerts, filters), [alerts, filters])
  const threat = useMemo(() => selectThreatLevel(alerts), [alerts])
  const selectedCategories: DetectionCategory[] = filters.type ? [filters.type.toLowerCase() as DetectionCategory] : []

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault()
        setPaletteOpen((open) => !open)
        return
      }
      if (paletteOpen || event.altKey || event.ctrlKey || event.metaKey || event.target instanceof HTMLElement && event.target.closest("input, textarea, select, [contenteditable=true]")) return
      const index = Number(event.key) - 1
      if (index >= 0 && index < SECTIONS.length) setSection(SECTIONS[index].id)
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [paletteOpen])

  useEffect(() => {
    if (lastRealAlert && lastRealAlert.id !== lastToastId.current && section !== "incidents") {
      setToastQueue((queue) => [lastRealAlert, ...queue.filter((item) => item.id !== lastRealAlert.id)].slice(0, MAX_TOASTS))
    }
    lastToastId.current = lastRealAlert?.id ?? null
  }, [lastRealAlert, section])

  const dismissToast = useCallback((alertId: string) => setToastQueue((queue) => queue.filter((item) => item.id !== alertId)), [])
  const clearToasts = useCallback(() => setToastQueue([]), [])

  // WT-25 (flagged hunk): open a deep-linked incident once it has arrived.
  useEffect(() => {
    const wanted = deepLinkAlertId.current
    if (!wanted) return
    const match = alerts.find((alert) => alert.id === wanted)
    if (!match) return
    deepLinkAlertId.current = null
    selectAlert(match)
    setSection("incidents")
  }, [alerts, selectAlert])

  // WT-25 (flagged hunk): minimal deep link. `?section=` / `?id=` are read after
  // mount (never during the render that the server also performs, which would be
  // a hydration mismatch) and `?section=` is kept in step with the visible section.
  const deepLinkAlertId = useRef<string | null>(null)
  const deepLinkApplied = useRef(false)
  useEffect(() => {
    if (!deepLinkApplied.current) {
      deepLinkApplied.current = true
      const link = readDeepLink()
      deepLinkAlertId.current = link.alertId
      if (link.section && link.section !== section) { setSection(link.section); return }
    }
    const next = new URLSearchParams(window.location.search)
    if (section === "overview") next.delete("section")
    else next.set("section", section)
    const search = next.toString()
    const target = window.location.pathname + (search ? `?${search}` : "") + window.location.hash
    const current = window.location.pathname + window.location.search + window.location.hash
    if (target !== current) window.history.replaceState(null, "", target)
  }, [section])

  const selectIncident = useCallback((alert: LiveAlert) => { selectAlert(alert); setSection("incidents") }, [selectAlert])
  const changeOverlaySettings = useCallback((settings: OverlaySettings) => {
    setOverlaySettings(settings)
    try { localStorage.setItem("ai-sentinel-overlay-settings", JSON.stringify(settings)) } catch { /* Local persistence is optional. */ }
  }, [])
  const stopDemo = useCallback(async (id: DemoSourceId) => {
    if (accessRole !== "admin") return
    try { await apiFetch(`${API_BASE}/demo_stop/${id}`, { method: "DELETE" }) } catch { /* Backend may already be offline. */ }
  }, [accessRole])
  const chooseDemo = useCallback(async (id: DemoSourceId) => {
    if (fixtureMode || connectionStatus !== "online") { setDemoSource(id); return }
    if (accessRole !== "admin") return
    if (activeDemoRef.current && activeDemoRef.current !== id) await stopDemo(activeDemoRef.current)
    const response = await apiFetch(`${API_BASE}/demo_start/${id}`, { method: "POST" })
    if (!response.ok) return
    activeDemoRef.current = id
    setDemoSource(id)
  }, [accessRole, connectionStatus, fixtureMode, stopDemo])
  useEffect(() => {
    const plan = section !== "demo-clips" ? buildDemoStopPlan(activeDemoRef.current) : null
    if (plan) {
      activeDemoRef.current = null
      void stopDemo(plan.immediateStopId)
      retryTimerRef.current = setTimeout(() => void stopDemo(plan.retryStopId), 500)
    }
    return () => { if (retryTimerRef.current) clearTimeout(retryTimerRef.current) }
  }, [section, stopDemo])
  useEffect(() => () => { if (activeDemoRef.current) void stopDemo(activeDemoRef.current) }, [stopDemo])

  const feed = <AlertFeed alerts={visibleAlerts} selectedAlertId={selectedAlert?.id ?? null} onSelectAlert={selectAlert} selectedCategories={selectedCategories} onCategoryChange={(categories) => setFilters({ ...filters, type: categories[0] === "weapon" ? "Weapon" : categories[0] === "violence" ? "Violence" : undefined })} />

  return <AppShell section={section} onSectionChange={setSection} collapsed={collapsed} onCollapsedChange={setCollapsed} connectionStatus={connectionStatus} threat={threat} privacyMode={privacyMode} onPrivacyToggle={() => setPrivacyMode((value) => !value)} onOpenPalette={() => setPaletteOpen(true)} fixtureMode={fixtureMode}>
    <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onNavigate={setSection} alerts={alerts} onSelectAlert={selectIncident} privacyMode={privacyMode} onTogglePrivacy={() => setPrivacyMode((value) => !value)} />
    <AlertToast alerts={toastQueue} activeTab={section} onNavigate={(alert) => { selectIncident(alert); dismissToast(alert.id) }} onDismiss={dismissToast} onDismissAll={clearToasts} />

    {section === "overview" && <Overview alerts={alerts} filters={filters} onFiltersChange={setFilters} connectionStatus={connectionStatus} fixtureMode={fixtureMode} onSelectIncident={selectIncident} onOpenMonitor={() => setSection("monitor")} />}

    {section === "monitor" && <UiMonitorSection mode="monitor" liveSource={liveSource} onLiveSourceChange={setLiveSource} demoSource={demoSource} onDemoSourceChange={(id) => void chooseDemo(id)} alerts={alerts} selectedAlert={selectedAlert} onSelectAlert={selectAlert} feed={feed} filters={filters} onFiltersChange={setFilters} privacyMode={privacyMode} personCount={personCount} overlaySettings={overlaySettings} onOverlaySettingsChange={changeOverlaySettings} fixtureMode={fixtureMode} connectionStatus={connectionStatus} canStartDemo={fixtureMode || connectionStatus !== "online" || accessRole === "admin"} />}

    {section === "demo-clips" && <UiMonitorSection mode="demo" liveSource={liveSource} onLiveSourceChange={setLiveSource} demoSource={demoSource} onDemoSourceChange={(id) => void chooseDemo(id)} alerts={alerts} selectedAlert={selectedAlert} onSelectAlert={selectAlert} feed={feed} filters={filters} onFiltersChange={setFilters} privacyMode={privacyMode} personCount={personCount} overlaySettings={overlaySettings} onOverlaySettingsChange={changeOverlaySettings} fixtureMode={fixtureMode} connectionStatus={connectionStatus} canStartDemo={fixtureMode || connectionStatus !== "online" || accessRole === "admin"} />}

    {section === "incidents" && <IncidentsSection alerts={visibleAlerts} selectedAlert={selectedAlert} onSelectAlert={selectAlert} filters={filters} onFiltersChange={setFilters} connectionStatus={connectionStatus} fixtureMode={fixtureMode} lastRealAlert={lastRealAlert} feed={feed} dossier={<IncidentPanel alert={selectedAlert} filters={filters} onFiltersChange={setFilters} privacyMode={privacyMode} fixtureMode={fixtureMode} connectionStatus={connectionStatus} />} related={<ClipSidebar alerts={visibleAlerts} selectedAlertId={selectedAlert?.id} selectedAlert={selectedAlert} onSelectAlert={selectAlert} fixtureMode={fixtureMode} connectionStatus={connectionStatus} filters={filters} privacyMode={privacyMode} />} />}

    {section === "intelligence" && <UiIntelOpsSection section="intelligence" />}

    {section === "operations" && <UiIntelOpsSection section="operations" />}

    {section === "system" && <UiIntelOpsSection section="system" />}
  </AppShell>
}

export default function DashboardPage() {
  return <SentinelProvider><Dashboard /></SentinelProvider>
}
