import assert from "node:assert/strict"
import test from "node:test"
import { reconnectDelayMs } from "../lib/reconnect-backoff.ts"

test("reconnect backoff grows exponentially, stays capped, and jitters within bounds", () => {
  const noJitter = { random: () => 0.5 }
  assert.deepEqual(
    [1, 2, 3, 4].map((attempt) => reconnectDelayMs(attempt, { baseMs: 1000, maxMs: 30_000, ...noJitter })),
    [1000, 2000, 4000, 8000],
  )
  assert.equal(reconnectDelayMs(20, { baseMs: 1000, maxMs: 30_000, ...noJitter }), 30_000)

  // Jitter spreads reconnect storms: delay stays inside ±jitterRatio of the step.
  const spread = Array.from({ length: 40 }, () => reconnectDelayMs(3, { baseMs: 1000, maxMs: 30_000, jitterRatio: 0.3 }))
  assert.ok(spread.every((delay) => delay >= 2800 && delay <= 5200), `out of jitter bounds: ${spread}`)
  assert.ok(new Set(spread).size > 1, "jitter must actually vary")
})

test("reconnect backoff tolerates degenerate attempts", () => {
  const noJitter = { random: () => 0.5 }
  assert.equal(reconnectDelayMs(0, noJitter), 1000)
  assert.equal(reconnectDelayMs(-3, noJitter), 1000)
  assert.equal(reconnectDelayMs(Number.NaN, noJitter), 1000)
})
