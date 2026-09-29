"use client"

import { useEffect, useState } from "react"
import { apiFetch, clearApiCredential, getApiCredential } from "@/lib/api-auth"
import { useSentinel } from "@/lib/sentinel-store"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

export type AccessState = "checking" | "unconfigured" | "required" | "verified" | "offline"

/** Reads the backend's operator-auth status once the event stream is online. */
export function useApiAccess() {
  const { connectionStatus, fixtureMode } = useSentinel()
  const offline = fixtureMode || connectionStatus !== "online"
  const [state, setState] = useState<AccessState>("checking")
  const [role, setRole] = useState<string | null>(null)
  const [expired, setExpired] = useState(false)

  useEffect(() => {
    if (offline) return
    let active = true
    apiFetch(`${API_BASE}/security/status`)
      .then(async response => {
        if (!response.ok) throw new Error("status unavailable")
        const status: { enabled?: boolean } = await response.json()
        if (!active) return
        if (!status.enabled) { setState("unconfigured"); return }
        if (!getApiCredential()) { setState("required"); return }
        const session = await apiFetch(`${API_BASE}/security/session`)
        if (!active) return
        if (!session.ok) { clearApiCredential(); setExpired(true); setState("required"); return }
        const data: { role?: unknown } = await session.json()
        if (!active) return
        setRole(typeof data.role === "string" ? data.role : null)
        setState("verified")
      })
      .catch(() => { if (active) setState("offline") })
    return () => { active = false }
  }, [offline])

  return { state: offline ? "offline" as const : state, setState, role, expired }
}
