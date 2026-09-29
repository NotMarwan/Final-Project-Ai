const SESSION_KEY = "ai-sentinel-api-key"
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const API_ORIGIN = new URL(API_BASE).origin

function sessionStore(): Storage | null {
  return typeof window === "undefined" ? null : window.sessionStorage
}

export function getApiCredential(): string {
  try {
    return sessionStore()?.getItem(SESSION_KEY)?.trim() ?? ""
  } catch {
    return ""
  }
}

export function saveApiCredential(value: string): void {
  const credential = value.trim()
  if (!credential) throw new Error("API key is required")
  sessionStore()?.setItem(SESSION_KEY, credential)
}

export function clearApiCredential(): void {
  try {
    sessionStore()?.removeItem(SESSION_KEY)
  } catch {
    // A disabled session store is equivalent to an empty session.
  }
}

export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const request = input instanceof Request ? input : null
  const target = request ?? new URL(input.toString(), API_BASE)
  const headers = new Headers(request?.headers)
  new Headers(init.headers).forEach((value, name) => headers.set(name, value))
  let targetsApi = false
  try {
    targetsApi = new URL(request?.url ?? target.toString()).origin === API_ORIGIN
  } catch {
    targetsApi = false
  }
  if (targetsApi) {
    headers.delete("X-API-Key")
    const credential = getApiCredential()
    if (credential) headers.set("X-API-Key", credential)
  } else {
    headers.delete("X-API-Key")
  }
  return fetch(target, { ...init, headers, ...(targetsApi ? { redirect: "error" as const } : {}) })
}

export async function downloadApiFile(input: RequestInfo | URL, filename: string): Promise<void> {
  const response = await apiFetch(input)
  if (!response.ok) throw new Error(`Download failed with HTTP ${response.status}`)
  const objectUrl = URL.createObjectURL(await response.blob())
  try {
    const anchor = document.createElement("a")
    anchor.href = objectUrl
    anchor.download = filename
    anchor.click()
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
  }
}
