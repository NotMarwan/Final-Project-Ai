import assert from "node:assert/strict"
import test from "node:test"

test("API credentials come only from tab storage and never from caller headers", async () => {
  const originalWindow = globalThis.window
  const originalFetch = globalThis.fetch
  let credential = "session-secret"
  const calls = []
  globalThis.window = {
    sessionStorage: {
      getItem: () => credential,
      setItem: () => {},
      removeItem: () => {},
    },
  }
  globalThis.fetch = async (input, init) => {
    calls.push({ input, headers: new Headers(init?.headers) })
    return new Response(null, { status: 204 })
  }

  try {
    const { apiFetch } = await import(`../api-auth.ts?test=${Date.now()}`)
    await apiFetch("/protected", { headers: { "X-API-Key": "caller-secret" } })
    credential = ""
    await apiFetch("/protected", { headers: { "X-API-Key": "caller-secret" } })
    await apiFetch("https://example.invalid/collect", { headers: { "X-API-Key": "caller-secret" } })
  } finally {
    globalThis.window = originalWindow
    globalThis.fetch = originalFetch
  }

  assert.equal(calls[0].headers.get("X-API-Key"), "session-secret")
  assert.equal(calls[1].headers.get("X-API-Key"), null)
  assert.equal(calls[2].headers.get("X-API-Key"), null)
})
