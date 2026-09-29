import type { MultiThreatData } from "./detection-types"

export type SourceVisualState = "live" | "replay" | "stale" | "offline" | "loading" | "unverified"

export function shouldPublishDetectionSnapshot(
  lastPublishedAt: number | null,
  receivedAt: number,
  previousDecision: string | null,
  nextDecision: string | null,
): boolean {
  return lastPublishedAt === null || receivedAt - lastPublishedAt >= 1_000 || previousDecision !== nextDecision
}

export function resolveEvidenceUrl(raw: string, apiBase: string): string | null {
  try {
    const url = new URL(raw, apiBase)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null
    return url.href
  } catch { return null }
}

export function evidenceFilename(id: string): string {
  return `${id.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 80) || 'evidence'}.mp4`
}

export function sourceVisualState(input: {
  connected: boolean
  stale: boolean
  inferenceStale: boolean
  frameReady: boolean
  failed?: boolean
  sourceKind: "live" | "file" | null
  isDemo: boolean
  externalPlayback: boolean
}): SourceVisualState {
  if (input.failed) return "offline"
  if (!input.frameReady) return input.connected || input.isDemo || input.externalPlayback ? "loading" : "offline"
  if (input.externalPlayback || (input.isDemo && !input.connected)) return "replay"
  if (!input.isDemo && input.sourceKind === null) return "unverified"
  if (input.stale || input.inferenceStale) return "stale"
  if (!input.connected) return input.sourceKind ? "stale" : "unverified"
  if (input.isDemo || input.externalPlayback || input.sourceKind === "file") return "replay"
  return input.sourceKind === "live" ? "live" : "unverified"
}

type OverlayColor = [number, number, number]
type OverlayBox = [number, number, number, number]
type VideoFitRect = {
  x: number
  y: number
  width: number
  height: number
  scale: number
}

type TrackLike = {
  id: string
  bbox: OverlayBox
  confidence: number
  color: OverlayColor
}

type DetectionOverlayDataLike = {
  tracks: TrackLike[]
  personCount: number
  isThreat: boolean
  threatConfidence: number
  fps: number
  weaponScore?: number
  videoWidth?: number
  videoHeight?: number
  multiThreat?: MultiThreatData
}

function areColorsEqual(a: OverlayColor, b: OverlayColor): boolean {
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2]
}

function areBoxesEqual(a: OverlayBox, b: OverlayBox): boolean {
  return a[0] === b[0] && a[1] === b[1] && a[2] === b[2] && a[3] === b[3]
}

export function normalizeScoreToPercent(score?: number | null): number {
  if (score == null || Number.isNaN(score)) return 0
  if (!Number.isFinite(score)) return 0
  return score <= 1 ? score * 100 : score
}

export function hasWeaponVisualSignal(
  rawWeaponScore?: number | null,
  multiThreat?: MultiThreatData,
): boolean {
  if (multiThreat?.hasWeapon) return true
  return normalizeScoreToPercent(rawWeaponScore) >= 30
}

export function getContainedVideoRect(
  containerWidth: number,
  containerHeight: number,
  videoWidth: number,
  videoHeight: number,
): VideoFitRect {
  const safeContainerWidth = Math.max(0, containerWidth)
  const safeContainerHeight = Math.max(0, containerHeight)
  const safeVideoWidth = Math.max(1, videoWidth)
  const safeVideoHeight = Math.max(1, videoHeight)
  const scale = Math.min(
    safeContainerWidth / safeVideoWidth || 0,
    safeContainerHeight / safeVideoHeight || 0,
  )
  const width = safeVideoWidth * scale
  const height = safeVideoHeight * scale

  return {
    x: cleanFloat((safeContainerWidth - width) / 2),
    y: cleanFloat((safeContainerHeight - height) / 2),
    width: cleanFloat(width),
    height: cleanFloat(height),
    scale: cleanFloat(scale),
  }
}

export function getCoveredVideoRect(
  containerWidth: number,
  containerHeight: number,
  videoWidth: number,
  videoHeight: number,
): VideoFitRect {
  const safeContainerWidth = Math.max(0, containerWidth)
  const safeContainerHeight = Math.max(0, containerHeight)
  const safeVideoWidth = Math.max(1, videoWidth)
  const safeVideoHeight = Math.max(1, videoHeight)
  const scale = Math.max(
    safeContainerWidth / safeVideoWidth || 0,
    safeContainerHeight / safeVideoHeight || 0,
  )
  const width = safeVideoWidth * scale
  const height = safeVideoHeight * scale

  return {
    x: cleanFloat((safeContainerWidth - width) / 2),
    y: cleanFloat((safeContainerHeight - height) / 2),
    width: cleanFloat(width),
    height: cleanFloat(height),
    scale: cleanFloat(scale),
  }
}

function isNormalizedBox(box: OverlayBox): boolean {
  return box.every((value) => value >= 0 && value <= 1)
}

function clampToRange(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value))
}

function cleanFloat(value: number): number {
  if (Math.abs(value) < 1e-9) return 0
  return Math.round(value * 1_000_000_000) / 1_000_000_000
}

export function projectOverlayBox(
  bbox: OverlayBox,
  videoRect: VideoFitRect,
  videoWidth: number,
  videoHeight: number,
): OverlayBox {
  const [x1, y1, x2, y2] = bbox
  if (isNormalizedBox(bbox)) {
    return [
      cleanFloat(videoRect.x + x1 * videoRect.width),
      cleanFloat(videoRect.y + y1 * videoRect.height),
      cleanFloat(videoRect.x + x2 * videoRect.width),
      cleanFloat(videoRect.y + y2 * videoRect.height),
    ]
  }

  const safeVideoWidth = Math.max(1, videoWidth)
  const safeVideoHeight = Math.max(1, videoHeight)
  return [
    cleanFloat(videoRect.x + clampToRange(x1, 0, safeVideoWidth) * videoRect.scale),
    cleanFloat(videoRect.y + clampToRange(y1, 0, safeVideoHeight) * videoRect.scale),
    cleanFloat(videoRect.x + clampToRange(x2, 0, safeVideoWidth) * videoRect.scale),
    cleanFloat(videoRect.y + clampToRange(y2, 0, safeVideoHeight) * videoRect.scale),
  ]
}

function areMultiThreatDataEqual(a?: MultiThreatData, b?: MultiThreatData): boolean {
  if (!a && !b) return true
  if (!a || !b) return false
  if (a.hasViolence !== b.hasViolence) return false
  if (a.hasWeapon !== b.hasWeapon) return false
  if (a.isMultiThreat !== b.isMultiThreat) return false
  if (a.violenceScore !== b.violenceScore) return false
  if (a.weaponScore !== b.weaponScore) return false
  if (a.fusedScore !== b.fusedScore) return false
  if (a.severity !== b.severity) return false
  if (a.reason !== b.reason) return false
  if (a.threatBoxes.length !== b.threatBoxes.length) return false

  for (let i = 0; i < a.threatBoxes.length; i += 1) {
    const left = a.threatBoxes[i]
    const right = b.threatBoxes[i]
    if (left.id !== right.id) return false
    if (left.type !== right.type) return false
    if (left.weaponType !== right.weaponType) return false
    if (left.confidence !== right.confidence) return false
    if (left.label !== right.label) return false
    if (!areBoxesEqual(left.bbox, right.bbox)) return false
    if (!areColorsEqual(left.color, right.color)) return false
  }

  return true
}

export function areDetectionOverlayDataEqual(
  a: DetectionOverlayDataLike,
  b: DetectionOverlayDataLike,
): boolean {
  if (a.personCount !== b.personCount) return false
  if (a.isThreat !== b.isThreat) return false
  if (a.threatConfidence !== b.threatConfidence) return false
  if (a.fps !== b.fps) return false
  if ((a.weaponScore ?? 0) !== (b.weaponScore ?? 0)) return false
  if ((a.videoWidth ?? 0) !== (b.videoWidth ?? 0)) return false
  if ((a.videoHeight ?? 0) !== (b.videoHeight ?? 0)) return false
  if (a.tracks.length !== b.tracks.length) return false

  for (let i = 0; i < a.tracks.length; i += 1) {
    const left = a.tracks[i]
    const right = b.tracks[i]
    if (left.id !== right.id) return false
    if (left.confidence !== right.confidence) return false
    if (!areBoxesEqual(left.bbox, right.bbox)) return false
    if (!areColorsEqual(left.color, right.color)) return false
  }

  return areMultiThreatDataEqual(a.multiThreat, b.multiThreat)
}

export function isToastSuppressedForTab(activeTab: string): boolean {
  return activeTab === "incidents"
}

export function buildDemoStopPlan<T extends string>(
  activeDemoId: T | null,
): { immediateStopId: T; retryStopId: T } | null {
  if (!activeDemoId) return null
  return {
    immediateStopId: activeDemoId,
    retryStopId: activeDemoId,
  }
}
