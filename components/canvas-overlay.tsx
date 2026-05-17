"use client"

import { useRef, useEffect, useCallback } from "react"
import type { MultiThreatData, ThreatBox } from "@/lib/detection-types"

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
}

interface CanvasOverlayProps {
  data: DetectionOverlayData | null
  videoWidth: number
  videoHeight: number
  containerWidth: number
  containerHeight: number
  showBoxes?: boolean
  showLabels?: boolean
  opacity?: number
  boxThickness?: number
  labelStyle?: "chip" | "plain"
}

const THREAT_VISUAL = {
  violence: {
    color: [239, 68, 68] as [number, number, number],
    boxStyle: "solid" as const,
    lineWidth: 3,
    glow: true,
    glowColor: "rgba(239, 68, 68, 0.6)",
    pulseSpeed: 500,
    icon: "\u26a0",
  },
  weapon_gun: {
    color: [220, 38, 38] as [number, number, number],
    boxStyle: "solid" as const,
    lineWidth: 3,
    glow: true,
    glowColor: "rgba(220, 38, 38, 0.6)",
    pulseSpeed: 500,
    icon: "\ud83d\udd2b",
  },
  weapon_knife: {
    color: [245, 158, 11] as [number, number, number],
    boxStyle: "solid" as const,
    lineWidth: 3,
    glow: true,
    glowColor: "rgba(245, 158, 11, 0.5)",
    pulseSpeed: 800,
    icon: "\ud83d\udd2a",
  },
  weapon_unknown: {
    color: [234, 179, 8] as [number, number, number],
    boxStyle: "dashed" as const,
    lineWidth: 2,
    glow: false,
    glowColor: "transparent",
    pulseSpeed: 1000,
    icon: "\u26a0",
  },
}

function getThreatVisualConfig(box: ThreatBox) {
  if (box.type === "violence") return THREAT_VISUAL.violence
  if (box.type === "weapon") {
    if (box.weaponType === "gun") return THREAT_VISUAL.weapon_gun
    if (box.weaponType === "knife") return THREAT_VISUAL.weapon_knife
    return THREAT_VISUAL.weapon_unknown
  }
  return THREAT_VISUAL.violence
}

function drawLabel(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  text: string, color: string, style: "chip" | "plain"
) {
  ctx.font = style === "chip"
    ? 'bold 12px "Segoe UI", Roboto, sans-serif'
    : 'bold 11px "Segoe UI", Roboto, sans-serif'
  ctx.textBaseline = "top"

  const metrics = ctx.measureText(text)
  const textW = metrics.width + 12
  const textH = style === "chip" ? 18 : 14
  const badgeY = Math.max(0, y - textH - 4)

  if (style === "chip") {
    ctx.fillStyle = color
    ctx.fillRect(x, badgeY, textW, textH)
    ctx.fillStyle = "#000"
    ctx.fillText(text, x + 6, badgeY + 3)
  } else {
    ctx.fillStyle = "rgba(0, 0, 0, 0.7)"
    ctx.fillRect(x, badgeY, textW, textH)
    ctx.fillStyle = "#fff"
    ctx.fillText(text, x + 4, badgeY + 2)
  }
}

export function CanvasOverlay({
  data,
  videoWidth,
  videoHeight,
  containerWidth,
  containerHeight,
  showBoxes = true,
  showLabels = true,
  opacity = 100,
  boxThickness = 2,
  labelStyle = "chip",
}: CanvasOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animFrameRef = useRef<number>(0)

  const scaleX = containerWidth / videoWidth
  const scaleY = containerHeight / videoHeight

  const draw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext("2d")
    if (!ctx) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    if (!data || !showBoxes) return

    ctx.lineWidth = boxThickness
    ctx.font = labelStyle === "chip"
      ? 'bold 12px "Segoe UI", Roboto, sans-serif'
      : 'bold 11px "Segoe UI", Roboto, sans-serif'
    ctx.textBaseline = "top"
    ctx.globalAlpha = opacity / 100

    data.tracks.forEach((track) => {
      const [x1, y1, x2, y2] = track.bbox
      const sx1 = x1 * scaleX
      const sy1 = y1 * scaleY
      const sx2 = x2 * scaleX
      const sy2 = y2 * scaleY
      const w = sx2 - sx1
      const h = sy2 - sy1
      const [r, g, b] = track.color
      const colorStr = `rgb(${r}, ${g}, ${b})`

      if (data.isThreat) {
        ctx.shadowColor = "rgba(255, 0, 0, 0.6)"
        ctx.shadowBlur = 12
      } else {
        ctx.shadowColor = "transparent"
        ctx.shadowBlur = 0
      }

      ctx.strokeStyle = colorStr
      ctx.strokeRect(sx1, sy1, w, h)

      const bracketLen = Math.min(15, w * 0.15, h * 0.15)
      ctx.beginPath()
      ctx.moveTo(sx1, sy1 + bracketLen); ctx.lineTo(sx1, sy1); ctx.lineTo(sx1 + bracketLen, sy1)
      ctx.moveTo(sx2, sy1 + bracketLen); ctx.lineTo(sx2, sy1); ctx.lineTo(sx2 - bracketLen, sy1)
      ctx.moveTo(sx1, sy2 - bracketLen); ctx.lineTo(sx1, sy2); ctx.lineTo(sx1 + bracketLen, sy2)
      ctx.moveTo(sx2, sy2 - bracketLen); ctx.lineTo(sx2, sy2); ctx.lineTo(sx2 - bracketLen, sy2)
      ctx.stroke()

      ctx.shadowBlur = 0

      if (showLabels) {
        const pct = (track.confidence * 100).toFixed(0)
        const labelText = labelStyle === "chip"
          ? `● ${track.id} ${pct}%`
          : `${track.id} ${pct}%`
        const textMetrics = ctx.measureText(labelText)
        const textW = textMetrics.width + 12
        const textH = labelStyle === "chip" ? 18 : 14
        const badgeY = Math.max(0, sy1 - textH - 4)

        if (labelStyle === "chip") {
          ctx.fillStyle = colorStr
          ctx.fillRect(sx1, badgeY, textW, textH)
          ctx.fillStyle = "#000"
          ctx.fillText(labelText, sx1 + 6, badgeY + 3)
        } else {
          ctx.fillStyle = "rgba(0, 0, 0, 0.7)"
          ctx.fillRect(sx1, badgeY, textW, textH)
          ctx.fillStyle = "#fff"
          ctx.fillText(labelText, sx1 + 4, badgeY + 2)
        }
      }
    })

    if (data.isThreat) {
      const pulse = 0.3 + 0.2 * Math.sin(Date.now() / 250)
      ctx.strokeStyle = `rgba(255, 0, 0, ${pulse})`
      ctx.lineWidth = 4
      ctx.strokeRect(2, 2, canvas.width - 4, canvas.height - 4)
    }

    // Draw threat boxes (multi-threat)
    if (data.multiThreat && data.multiThreat.threatBoxes.length > 0) {
      const time = Date.now()

      data.multiThreat.threatBoxes.forEach((box) => {
        const vis = getThreatVisualConfig(box)
        const [x1, y1, x2, y2] = box.bbox
        const sx1 = x1 * scaleX
        const sy1 = y1 * scaleY
        const sx2 = x2 * scaleX
        const sy2 = y2 * scaleY
        const w = sx2 - sx1
        const h = sy2 - sy1
        const [r, g, b] = vis.color
        const colorStr = "rgb(" + r + ", " + g + ", " + b + ")"

        if (vis.glow) {
          const pulse = 0.4 + 0.3 * Math.sin(time / vis.pulseSpeed)
          ctx.shadowColor = vis.glowColor
          ctx.shadowBlur = 12 * pulse
        }

        ctx.strokeStyle = colorStr
        ctx.lineWidth = vis.lineWidth
        ctx.globalAlpha = (opacity / 100) * 0.9

        if (vis.boxStyle === "dashed") {
          ctx.setLineDash([6, 4])
          ctx.strokeRect(sx1, sy1, w, h)
          ctx.setLineDash([])
        } else {
          ctx.strokeRect(sx1, sy1, w, h)
        }

        // Corner brackets (threat style)
        const bracketLen = Math.min(20, w * 0.2, h * 0.2)
        ctx.lineWidth = vis.lineWidth + 1
        ctx.beginPath()
        ctx.moveTo(sx1, sy1 + bracketLen); ctx.lineTo(sx1, sy1); ctx.lineTo(sx1 + bracketLen, sy1)
        ctx.moveTo(sx2, sy1 + bracketLen); ctx.lineTo(sx2, sy1); ctx.lineTo(sx2 - bracketLen, sy1)
        ctx.moveTo(sx1, sy2 - bracketLen); ctx.lineTo(sx1, sy2); ctx.lineTo(sx1 + bracketLen, sy2)
        ctx.moveTo(sx2, sy2 - bracketLen); ctx.lineTo(sx2, sy2); ctx.lineTo(sx2 - bracketLen, sy2)
        ctx.stroke()

        ctx.shadowBlur = 0

        if (showLabels) {
          const label = vis.icon + " " + box.label + " " + (box.confidence * 100).toFixed(0) + "%"
          drawLabel(ctx, sx1, sy1, w, h, label, colorStr, labelStyle)
        }
      })

      // Draw trajectory line if multiple threat positions
      if (data.multiThreat.threatBoxes.length >= 2) {
        ctx.beginPath()
        ctx.strokeStyle = "rgba(239, 68, 68, 0.4)"
        ctx.lineWidth = 2
        ctx.setLineDash([4, 4])

        data.multiThreat.threatBoxes.forEach((box, i) => {
          const cx = ((box.bbox[0] + box.bbox[2]) / 2) * scaleX
          const cy = ((box.bbox[1] + box.bbox[3]) / 2) * scaleY
          if (i === 0) ctx.moveTo(cx, cy)
          else ctx.lineTo(cx, cy)
        })

        ctx.stroke()
        ctx.setLineDash([])
      }

      // Draw threat pulse border (override the simpler isThreat one)
      const mtPulse = 0.3 + 0.2 * Math.sin(time / 250)
      ctx.strokeStyle = "rgba(239, 68, 68, " + mtPulse + ")"
      ctx.lineWidth = 4
      ctx.strokeRect(2, 2, canvas.width - 4, canvas.height - 4)
    }

    ctx.globalAlpha = 1
  }, [data, scaleX, scaleY, showBoxes, showLabels, boxThickness, labelStyle, opacity])

  useEffect(() => {
    const animate = () => {
      draw()
      animFrameRef.current = requestAnimationFrame(animate)
    }
    animFrameRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animFrameRef.current)
  }, [draw])

  return (
    <canvas
      ref={canvasRef}
      width={containerWidth}
      height={containerHeight}
      className="absolute inset-0 z-10 pointer-events-none"
      style={{ imageRendering: "crisp-edges" }}
    />
  )
}