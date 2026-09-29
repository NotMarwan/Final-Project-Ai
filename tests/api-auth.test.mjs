import test from "node:test"
import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"

const root = new URL("../", import.meta.url)

async function source(path) {
  return readFile(new URL(path, root), "utf8")
}

test("the UI credential stays in tab-scoped storage and is attached centrally", async () => {
  const auth = await source("lib/api-auth.ts")
  assert.match(auth, /window\.sessionStorage/)
  assert.match(auth, /headers\.set\("X-API-Key", credential\)/)
  assert.doesNotMatch(auth, /localStorage/)
  assert.doesNotMatch(auth, /NEXT_PUBLIC_(?:ADMIN_)?API_KEY/)
})

test("the API key is never forwarded to an external origin", async () => {
  const calls = []
  const originalWindow = globalThis.window
  const originalFetch = globalThis.fetch
  globalThis.window = {
    sessionStorage: {
      getItem: () => "tab-secret",
      setItem: () => {},
      removeItem: () => {},
    },
    setTimeout,
  }
  globalThis.fetch = async (input, init) => {
    calls.push({ input, headers: new Headers(init?.headers) })
    return new Response(null, { status: 204 })
  }
  try {
    const { apiFetch } = await import(`../lib/api-auth.ts?test=${Date.now()}`)
    await apiFetch("/security/session")
    await apiFetch(
      new Request("http://localhost:8002/audio/analyze", {
        headers: { "Content-Type": "application/json", "X-Test": "request" },
      }),
      { headers: { "X-Test": "override" } },
    )
    await apiFetch("https://example.invalid/collect", { headers: { "X-API-Key": "caller-secret" } })
  } finally {
    globalThis.window = originalWindow
    globalThis.fetch = originalFetch
  }
  assert.equal(calls[0].input.toString(), "http://localhost:8002/security/session")
  assert.equal(calls[0].headers.get("X-API-Key"), "tab-secret")
  assert.equal(calls[1].headers.get("Content-Type"), "application/json")
  assert.equal(calls[1].headers.get("X-Test"), "override")
  assert.equal(calls[2].headers.get("X-API-Key"), null)
})

test("protected UI calls use the authenticated fetch helper", async () => {
  for (const path of [
    "app/page.tsx",
    "components/ai-report.tsx",
    "components/alert-history.tsx",
    "components/category-filter.tsx",
    "components/clip-sidebar.tsx",
    "components/incident-panel.tsx",
    "components/telegram-status.tsx",
    "components/video-player.tsx",
    "components/webrtc-player.tsx",
  ]) {
    const text = await source(path)
    assert.match(text, /apiFetch|downloadApiFile/, `${path} must use the authenticated request helper`)
    assert.doesNotMatch(text, /NEXT_PUBLIC_(?:ADMIN_)?API_KEY/, `${path} must not bundle a key`)
  }
})

test("native streams remain header-free and the access prompt is mounted", async () => {
  const store = await source("lib/sentinel-store.tsx")
  assert.match(store, /new EventSource\(SSE_URL\)/)

  const shell = await source("components/shell/app-shell.tsx")
  assert.match(shell, /<AccessNotice /, "every section must surface the operator-key requirement")
  const system = await source("components/sections/ui-intel-ops-section.tsx")
  assert.match(system, /<ApiAccess \/>/)

  const player = await source("components/video-player.tsx")
  assert.match(player, /\/video_feed\?camera_id=/)
})
