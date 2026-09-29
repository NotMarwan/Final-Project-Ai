"use client"

import { useCallback, useEffect, useRef, type RefObject } from "react"
import type { MultiThreatData } from "@/lib/detection-types"
import { isOverlayFrameCorrelated } from "@/lib/detection-envelope"
import { getContainedVideoRect, getCoveredVideoRect, projectOverlayBox } from "@/lib/live-visual-state"

export interface TrackOverlay {
  id: string
  bbox: [number, number, number, number]
  confidence: number
  color: [number, number, number]
}

export interface DetectionOverlayData {
  tracks: TrackOverlay[]
  personCount: number
  isThreat: boolean
  threatConfidence: number
  fps: number
  weaponScore?: number
  videoWidth?: number
  videoHeight?: number
  multiThreat?: MultiThreatData
  /** WT-17 (SC-3 additive): display-frame identity of this overlay snapshot. */
  frameSequence?: number
}

type Props = {
  data: DetectionOverlayData | null
  dataRef?: RefObject<DetectionOverlayData | null>
  videoWidth: number
  videoHeight: number
  containerWidth: number
  containerHeight: number
  showBoxes?: boolean
  showLabels?: boolean
  opacity?: number
  boxThickness?: number
  labelStyle?: "chip" | "plain"
  fitMode?: "contain" | "cover"
  /**
   * WT-17 (S-09): identity of the frame currently displayed by the transport.
   * Without it (plain <img> MJPEG) correlation cannot be proven and the overlay
   * hides itself — a hidden overlay is never misaligned.
   */
  displayFrameSequence?: number | null
}

const FONT = '600 12px "IBM Plex Sans Arabic", sans-serif'
const VALID_BOX = (bbox: number[]) => bbox.length === 4 && bbox.every(Number.isFinite)

function drawBox(ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, tone: string, thickness: number) {
  const width = Math.max(0, x2 - x1)
  const height = Math.max(0, y2 - y1)
  if (!width || !height) return
  ctx.lineWidth = thickness
  ctx.strokeStyle = tone
  ctx.strokeRect(x1 + .5, y1 + .5, width - 1, height - 1)
  const bracket = Math.min(18, width * .18, height * .18)
  ctx.lineWidth = thickness + 1
  ctx.beginPath()
  ctx.moveTo(x1, y1 + bracket); ctx.lineTo(x1, y1); ctx.lineTo(x1 + bracket, y1)
  ctx.moveTo(x2 - bracket, y1); ctx.lineTo(x2, y1); ctx.lineTo(x2, y1 + bracket)
  ctx.moveTo(x1, y2 - bracket); ctx.lineTo(x1, y2); ctx.lineTo(x1 + bracket, y2)
  ctx.moveTo(x2 - bracket, y2); ctx.lineTo(x2, y2); ctx.lineTo(x2, y2 - bracket)
  ctx.stroke()
}

function drawLabel(ctx: CanvasRenderingContext2D, x: number, y: number, label: string, tone: string, style: "chip" | "plain", background: string, foreground: string) {
  ctx.font = FONT
  ctx.textBaseline = "middle"
  ctx.direction = "rtl"
  const width = Math.ceil(ctx.measureText(label).width) + 15
  const height = style === "chip" ? 22 : 20
  const top = y >= height + 5 ? y - height - 3 : y + 3
  ctx.fillStyle = style === "chip" ? tone : background
  ctx.fillRect(x, top, width, height)
  ctx.fillStyle = style === "chip" ? background : foreground
  ctx.fillText(label, x + width - 7, top + height / 2)
  ctx.direction = "inherit"
}

export function CanvasOverlay({ data, dataRef, videoWidth, videoHeight, containerWidth, containerHeight, showBoxes = true, showLabels = true, opacity = 100, boxThickness = 2, labelStyle = "chip", fitMode = "contain", displayFrameSequence = null }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const lastDrawnRef = useRef<DetectionOverlayData | null>(null)
  const frameRef = useRef<number>(0)

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    const frame = dataRef?.current ?? data
    if (!canvas || lastDrawnRef.current === frame) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return
    const dpr = Math.max(1, window.devicePixelRatio || 1)
    const width = Math.max(1, Math.round(containerWidth))
    const height = Math.max(1, Math.round(containerHeight))
    const targetWidth = Math.round(width * dpr)
    const targetHeight = Math.round(height * dpr)
    if (canvas.width !== targetWidth || canvas.height !== targetHeight) { canvas.width = targetWidth; canvas.height = targetHeight }
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, width, height)
    lastDrawnRef.current = frame
    // WT-17 (S-09): never draw an overlay that cannot be proven to belong to the
    // frame on screen — hidden beats misaligned.
    if (!frame || !isOverlayFrameCorrelated(frame.frameSequence, displayFrameSequence) || (!showBoxes && !showLabels)) return

    const css = getComputedStyle(canvas)
    const weapon = css.getPropertyValue("--cat-weapon").trim()
    const violence = css.getPropertyValue("--cat-violence").trim()
    const person = css.getPropertyValue("--signal").trim()
    const background = css.getPropertyValue("--surface-0").trim()
    const foreground = css.getPropertyValue("--text-primary").trim()
    const rect = fitMode === "cover"
      ? getCoveredVideoRect(width, height, videoWidth, videoHeight)
      : getContainedVideoRect(width, height, videoWidth, videoHeight)
    ctx.globalAlpha = Math.min(1, Math.max(0, opacity / 100))
    for (const track of frame.tracks) {
      if (!VALID_BOX(track.bbox)) continue
      const [x1, y1, x2, y2] = projectOverlayBox(track.bbox, rect, videoWidth, videoHeight)
      if (showBoxes) drawBox(ctx, x1, y1, x2, y2, person, boxThickness)
      if (showLabels) drawLabel(ctx, x1, y1, `شخص ${track.id} · ${Math.round(track.confidence * 100)}%`, person, labelStyle, background, foreground)
    }
    for (const box of frame.multiThreat?.threatBoxes ?? []) {
      if (!VALID_BOX(box.bbox)) continue
      const tone = box.type === "weapon" ? weapon : violence
      const [x1, y1, x2, y2] = projectOverlayBox(box.bbox, rect, videoWidth, videoHeight)
      if (showBoxes) drawBox(ctx, x1, y1, x2, y2, tone, Math.max(2, boxThickness + 1))
      if (showLabels) drawLabel(ctx, x1, y1, `${box.type === "weapon" ? "مؤشر سلاح" : "مؤشر اعتداء"} · ${Math.round(box.confidence * 100)}%`, tone, labelStyle, background, foreground)
    }
    ctx.globalAlpha = 1
  }, [boxThickness, containerHeight, containerWidth, data, dataRef, displayFrameSequence, fitMode, labelStyle, opacity, showBoxes, showLabels, videoHeight, videoWidth])

  useEffect(() => {
    lastDrawnRef.current = null
    const paint = () => { draw(); frameRef.current = requestAnimationFrame(paint) }
    frameRef.current = requestAnimationFrame(paint)
    return () => cancelAnimationFrame(frameRef.current)
  }, [draw])

  // WT-17 (S-09): without a display-side frame identity the overlay hides itself.
  if (displayFrameSequence === null || displayFrameSequence === undefined) return null
  return <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 z-10" aria-hidden="true" />
}
