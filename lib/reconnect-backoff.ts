/**
 * WT-17 (S-09): exponential reconnect backoff with jitter, shared by the MJPEG
 * <img> restart loop, the /detections SSE reconnect and the WHEP client.
 *
 * Deterministic when `random` is injected (tests); the jitter spreads reconnect
 * storms so parallel clients do not hammer a recovering server in lock-step.
 */
export type BackoffOptions = {
  baseMs?: number
  maxMs?: number
  jitterRatio?: number
  random?: () => number
}

export function reconnectDelayMs(attempt: number, options: BackoffOptions = {}): number {
  const { baseMs = 1_000, maxMs = 30_000, jitterRatio = 0.3, random = Math.random } = options
  const safeAttempt = Number.isFinite(attempt) && attempt > 0 ? Math.floor(attempt) : 1
  const exponential = Math.min(maxMs, baseMs * 2 ** (safeAttempt - 1))
  const jitterSpan = exponential * Math.max(0, Math.min(1, jitterRatio))
  const jitter = (random() * 2 - 1) * jitterSpan
  return Math.max(baseMs / 2, Math.round(exponential + jitter))
}
