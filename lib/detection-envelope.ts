import type { MultiThreatData, ThreatBox } from "./detection-types"

type DetectionTrack = {
  id: string
  bbox: [number, number, number, number]
  confidence: number
  color: [number, number, number]
}

export type DetectionOverlayEnvelope = {
  tracks: DetectionTrack[]
  personCount: number
  isThreat: boolean
  threatConfidence: number
  fps: number
  weaponScore?: number
  videoWidth?: number
  videoHeight?: number
  multiThreat?: MultiThreatData
  /** WT-17 (SC-3 additive): display-frame identity of the rendered snapshot. */
  frameSequence?: number
}

/**
 * WT-17 (S-09): the client overlay may draw ONLY when the payload's frameSequence
 * is proven identical to the frame currently displayed. Missing or mismatched
 * correlation hides the overlay — a hidden overlay beats a misaligned one.
 */
export function isOverlayFrameCorrelated(
  payloadFrameSequence: number | null | undefined,
  displayFrameSequence: number | null | undefined,
): boolean {
  return typeof payloadFrameSequence === "number" && Number.isSafeInteger(payloadFrameSequence)
    && payloadFrameSequence > 0 && payloadFrameSequence === displayFrameSequence
}

const MAX_TRACKS = 256
const MAX_BOX_COORDINATE = 1_000_000
const MAX_DIMENSION = 65_536
const MAX_DISPLAY_TEXT = 128
const SEVERITIES = new Set(["low", "medium", "high", "critical"])
const WEAPON_TYPES = new Set(["gun", "knife", "explosive", "unknown"])

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null
}

function boundedNumber(value: unknown, min: number, max: number): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max
}

function displayText(value: unknown): value is string {
  return typeof value === "string" && value.length <= MAX_DISPLAY_TEXT
}

function parseBox(value: unknown): [number, number, number, number] | null {
  if (!Array.isArray(value) || value.length !== 4
    || !value.every((coordinate) => boundedNumber(coordinate, 0, MAX_BOX_COORDINATE))) return null
  return [value[0], value[1], value[2], value[3]]
}

function parseColor(value: unknown): [number, number, number] | null {
  if (!Array.isArray(value) || value.length !== 3
    || !value.every((channel) => Number.isInteger(channel) && boundedNumber(channel, 0, 255))) return null
  return [value[0], value[1], value[2]]
}

function parseTrack(value: unknown): DetectionTrack | null {
  const track = asRecord(value)
  if (!track || !displayText(track.id) || !track.id
    || !boundedNumber(track.confidence, 0, 1)) return null
  const bbox = parseBox(track.bbox)
  const color = parseColor(track.color)
  return bbox && color ? { id: track.id, bbox, confidence: track.confidence, color } : null
}

function parseThreatBox(value: unknown): ThreatBox | null {
  const box = asRecord(value)
  if (!box || !displayText(box.id) || !box.id
    || (box.type !== "violence" && box.type !== "weapon")
    || !boundedNumber(box.confidence, 0, 1)
    || !displayText(box.label)) return null
  const bbox = parseBox(box.bbox)
  const color = parseColor(box.color)
  if (!bbox || !color) return null
  const weaponType = WEAPON_TYPES.has(String(box.weaponType))
    ? box.weaponType as ThreatBox["weaponType"] : undefined
  return {
    id: box.id,
    type: box.type,
    ...(weaponType ? { weaponType } : {}),
    bbox,
    confidence: box.confidence,
    color,
    label: box.label,
  }
}

function parseMultiThreat(value: unknown): MultiThreatData | null {
  const threat = asRecord(value)
  if (!threat) return null
  const rawBoxes = threat.threatBoxes ?? []
  if (!Array.isArray(rawBoxes) || rawBoxes.length > MAX_TRACKS) return null
  const boxes = rawBoxes.map(parseThreatBox)
  if (boxes.some((box) => box === null)) return null
  if ((threat.hasViolence !== undefined && typeof threat.hasViolence !== "boolean")
    || (threat.hasWeapon !== undefined && typeof threat.hasWeapon !== "boolean")
    || (threat.isMultiThreat !== undefined && typeof threat.isMultiThreat !== "boolean")) return null
  for (const key of ["violenceScore", "weaponScore", "fusedScore"]) {
    if (threat[key] !== undefined && !boundedNumber(threat[key], 0, 100)) return null
  }
  if (threat.severity !== undefined && threat.severity !== "none" && !SEVERITIES.has(String(threat.severity))) return null
  if (threat.reason !== undefined && !displayText(threat.reason)) return null
  return {
    hasViolence: threat.hasViolence === true,
    hasWeapon: threat.hasWeapon === true,
    isMultiThreat: threat.isMultiThreat === true,
    violenceScore: (threat.violenceScore as number | undefined) ?? 0,
    weaponScore: (threat.weaponScore as number | undefined) ?? 0,
    fusedScore: (threat.fusedScore as number | undefined) ?? 0,
    severity: threat.severity === "none" ? "medium"
      : (threat.severity as MultiThreatData["severity"] | undefined) ?? "medium",
    threatBoxes: boxes as ThreatBox[],
    reason: (threat.reason as string | undefined) ?? "",
  }
}

function readOptionalNumber(
  data: Record<string, unknown>,
  key: string,
  min: number,
  max: number,
): number | undefined | null {
  if (data[key] === undefined || data[key] === null) return undefined
  return boundedNumber(data[key], min, max) ? data[key] : null
}

/** Fail closed on malformed SSE data before values reach the canvas or React tree. */
export function parseDetectionOverlayEnvelope(value: unknown): DetectionOverlayEnvelope | null {
  const data = asRecord(value)
  if (!data || !Array.isArray(data.tracks) || data.tracks.length > MAX_TRACKS) return null
  const tracks = data.tracks.map(parseTrack)
  if (tracks.some((track) => track === null)) return null

  const personCount = data.personCount === undefined || data.personCount === null ? 0 : data.personCount
  const isThreat = data.isThreat === undefined || data.isThreat === null ? false : data.isThreat
  if (!Number.isSafeInteger(personCount) || (personCount as number) < 0 || typeof isThreat !== "boolean") return null

  const threatConfidence = readOptionalNumber(data, "threatConfidence", 0, 100)
  const fps = readOptionalNumber(data, "fps", 0, 1000)
  const weaponScore = readOptionalNumber(data, "weaponScore", 0, 100)
  const readDimension = (key: string) => data[key] === 0
    ? undefined : readOptionalNumber(data, key, 1, MAX_DIMENSION)
  const videoWidth = readDimension("videoWidth")
  const videoHeight = readDimension("videoHeight")
  if (threatConfidence === null || fps === null || weaponScore === null || videoWidth === null || videoHeight === null) return null

  const multiThreat = data.multiThreat === undefined || data.multiThreat === null || data.multiThreat === false
    ? undefined : parseMultiThreat(data.multiThreat)
  if (data.multiThreat != null && data.multiThreat !== false && !multiThreat) return null

  // WT-17 (SC-3 additive): frame identity fails closed like every other field —
  // a malformed frameSequence rejects the envelope so the overlay stays hidden.
  let frameSequence: number | undefined
  if (data.frameSequence !== undefined && data.frameSequence !== null) {
    const value = data.frameSequence
    if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) return null
    frameSequence = value
  }
  return {
    tracks: tracks as DetectionTrack[],
    personCount: personCount as number,
    isThreat,
    threatConfidence: threatConfidence ?? 0,
    fps: fps ?? 0,
    ...(weaponScore !== undefined ? { weaponScore } : {}),
    ...(videoWidth !== undefined ? { videoWidth } : {}),
    ...(videoHeight !== undefined ? { videoHeight } : {}),
    ...(multiThreat ? { multiThreat } : {}),
    ...(frameSequence !== undefined ? { frameSequence } : {}),
  }
}
