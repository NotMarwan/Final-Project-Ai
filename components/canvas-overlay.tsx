"use client"

import { useRef, useEffect, useCallback } from "react"

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