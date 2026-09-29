"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from "react"
import type { ReactNode } from "react"
import type { LiveAlert } from "@/components/video-player"
import { apiFetch } from "./api-auth"
import {
  mergeTriageRecord, parseStreamFrame, parseTriageRecord, triageActionRecord,
  type CrossFilters, type TriageAction, type TriageRecord,
} from "./sentinel-selectors"
import { reconnectDelayMs } from "./reconnect-backoff"
import { fixturesEnabled, makeUiFixtures } from "./ui-fixtures"

export type ConnectionStatus = "online" | "reconnecting" | "offline"
/** How a triage transition was committed: the API persisted it, or the browser
 *  session holds it (offline / unauthorized / fixture preview). */
export type TriageOutcome = "server" | "session" | "rejected"
type State = {
  alerts: LiveAlert[]
  selectedAlert: LiveAlert | null
  connectionStatus: ConnectionStatus
  personCount: number
  filters: CrossFilters
  fixtureMode: boolean
  lastRealAlert: LiveAlert | null
  /** Newest triage record per alert id (WT-25 additive). */
  triage: Record<string, TriageRecord>
  /** Alert-shaped SSE frames the parser rejected (visible, never silent). */
  rejectedEnvelopes: number
}
type Action =
  | { type: "alert"; alert: LiveAlert }
  | { type: "select"; alert: LiveAlert | null }
  | { type: "connection"; status: ConnectionStatus }
  | { type: "person"; count: number }
  | { type: "filters"; filters: CrossFilters }
  | { type: "fixtures"; alerts: LiveAlert[] }
  | { type: "triage"; alertId: string; record: TriageRecord }
  | { type: "triage-action"; alertId: string; action: TriageAction; actor: string }
  | { type: "envelope-rejected" }

const initialState: State = {
  alerts: [], selectedAlert: null, connectionStatus: "offline", personCount: 0,
  filters: { range: "1h" }, fixtureMode: false, lastRealAlert: null,
  triage: {}, rejectedEnvelopes: 0,
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "alert":
      if (state.alerts.some((item) => item.id === action.alert.id)) return state
      return {
        ...state,
        alerts: [action.alert, ...state.alerts].slice(0, 50),
        selectedAlert: action.alert,
        lastRealAlert: action.alert,
      }
    case "select": return { ...state, selectedAlert: action.alert }
    case "connection": return { ...state, connectionStatus: action.status }
    case "person": return { ...state, personCount: action.count }
    case "filters": return { ...state, filters: action.filters }
    case "fixtures": return { ...state, fixtureMode: true, alerts: action.alerts, selectedAlert: action.alerts[0] ?? null }
    case "triage": return { ...state, triage: mergeTriageRecord(state.triage, action.alertId, action.record) }
    case "triage-action": {
      const record = triageActionRecord(state.triage[action.alertId], action.action, action.actor, Date.now())
      if (record === null) return state
      return { ...state, triage: mergeTriageRecord(state.triage, action.alertId, record) }
    }
    case "envelope-rejected": return { ...state, rejectedEnvelopes: state.rejectedEnvelopes + 1 }
  }
}

type Store = State & {
  selectAlert: (alert: LiveAlert | null) => void
  setFilters: (filters: CrossFilters) => void
  /** Applies a triage transition: optimistic session record first, then the
   *  server's authoritative record when the API accepts it. */
  recordTriage: (alertId: string, action: TriageAction, actor: string) => Promise<TriageOutcome>
  /** Loads the process-scoped triage record for one alert (incident dossier
   *  hydration; does nothing when the API is unavailable). */
  hydrateTriage: (alertId: string) => Promise<void>
}
const SentinelContext = createContext<Store | null>(null)
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const SSE_URL = process.env.NEXT_PUBLIC_SSE_URL ?? `${API_BASE}/alerts`

export function SentinelProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  const fixtureRef = useRef(false)

  useEffect(() => {
    if (fixturesEnabled(window.location.search)) {
      fixtureRef.current = true
      dispatch({ type: "fixtures", alerts: makeUiFixtures(Date.now()) })
    }
  }, [])

  useEffect(() => {
    let stopped = false
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined
    let graceTimer: ReturnType<typeof setTimeout> | undefined
    let source: EventSource | undefined
    // WT-17 (S-09): reconnect-storm safety — exponential backoff + jitter (this file
    // has no visible owner in the campaign split; hunk is flagged for the integrator).
    let reconnectAttempt = 0
    const connect = () => {
      if (stopped) return
      const currentSource = new EventSource(SSE_URL)
      source = currentSource
      currentSource.onopen = () => {
        if (stopped || source !== currentSource) return
        reconnectAttempt = 0
        clearTimeout(graceTimer)
        graceTimer = undefined
        dispatch({ type: "connection", status: "online" })
      }
      currentSource.onmessage = (event) => {
        if (stopped || source !== currentSource) return
        const frame = parseStreamFrame(event.data)
        if (frame.kind === "alert") { if (!fixtureRef.current) dispatch({ type: "alert", alert: frame.alert }) }
        else if (frame.kind === "person") dispatch({ type: "person", count: frame.count })
        else if (frame.kind === "triage") dispatch({ type: "triage", alertId: frame.alertId, record: frame.record })
        else if (frame.kind === "rejected") dispatch({ type: "envelope-rejected" })
      }
      currentSource.onerror = () => {
        if (stopped || source !== currentSource) return
        source = undefined
        dispatch({ type: "connection", status: "reconnecting" })
        currentSource.close()
        clearTimeout(graceTimer)
        graceTimer = setTimeout(() => {
          graceTimer = undefined
          if (!stopped && !source) dispatch({ type: "connection", status: "offline" })
        }, 2_000)
        clearTimeout(reconnectTimer)
        // WT-17 (S-09): exponential backoff + jitter (was a fixed 3_000 ms retry).
        reconnectAttempt += 1
        reconnectTimer = setTimeout(() => {
          reconnectTimer = undefined
          connect()
        }, reconnectDelayMs(reconnectAttempt))
      }
    }
    connect()
    return () => {
      stopped = true
      source?.close()
      source = undefined
      clearTimeout(reconnectTimer)
      clearTimeout(graceTimer)
    }
  }, [])

  const selectAlert = useCallback((alert: LiveAlert | null) => dispatch({ type: "select", alert }), [])
  const setFilters = useCallback((filters: CrossFilters) => dispatch({ type: "filters", filters }), [])
  const triageRef = useRef(state.triage)
  useEffect(() => { triageRef.current = state.triage }, [state.triage])

  const recordTriage = useCallback(async (alertId: string, action: TriageAction, actor: string): Promise<TriageOutcome> => {
    if (triageActionRecord(triageRef.current[alertId], action, actor, Date.now()) === null) return "rejected"
    dispatch({ type: "triage-action", alertId, action, actor })
    try {
      const response = await apiFetch(`${API_BASE}/alerts/${encodeURIComponent(alertId)}/triage`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }),
      })
      if (!response.ok) throw new Error("triage not persisted")
      const record = parseTriageRecord(await response.json())
      if (!record) throw new Error("invalid triage record")
      dispatch({ type: "triage", alertId, record })
      return "server"
    } catch { return "session" }
  }, [])

  const hydrateTriage = useCallback(async (alertId: string) => {
    try {
      const response = await apiFetch(`${API_BASE}/alerts/${encodeURIComponent(alertId)}/triage`)
      if (!response.ok) return
      const payload: unknown = await response.json()
      const record = parseTriageRecord(payload && typeof payload === "object" && !Array.isArray(payload)
        ? (payload as Record<string, unknown>).triage
        : null)
      if (record) dispatch({ type: "triage", alertId, record })
    } catch { /* Offline or unauthorized: the session record stays authoritative. */ }
  }, [])

  const value = useMemo(() => ({ ...state, selectAlert, setFilters, recordTriage, hydrateTriage }), [state, selectAlert, setFilters, recordTriage, hydrateTriage])
  return <SentinelContext.Provider value={value}>{children}</SentinelContext.Provider>
}

export function useSentinel(): Store {
  const store = useContext(SentinelContext)
  if (!store) throw new Error("SentinelProvider is required")
  return store
}
