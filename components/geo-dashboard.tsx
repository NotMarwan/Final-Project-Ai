"use client"

import { memo } from "react"
import { Camera, MapPinned, Radar, ShieldAlert, Sparkles, Activity } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { LiveAlert } from "@/components/video-player"

interface GeoDashboardProps {
  alert: LiveAlert | null
  alerts: LiveAlert[]
  focusCameraId: string
}

const CAMERA_POINTS = [
  { id: "CAM-01", label: "North Hall", x: 24, y: 22, accent: "emerald" },
  { id: "CAM-02", label: "Atrium", x: 60, y: 56, accent: "amber" },
  { id: "CAM-03", label: "South Exit", x: 86, y: 28, accent: "rose" },
] as const

export const GeoDashboard = memo(function GeoDashboard({ alert, alerts, focusCameraId }: GeoDashboardProps) {
  const activeCameraId = alert?.cameraId ?? focusCameraId
  const criticalCount = alerts.filter((item) => item.severity === "critical").length
  const highCount = alerts.filter((item) => item.severity === "high").length

  const cameraIndex = CAMERA_POINTS.find((item) => item.id === activeCameraId) ?? CAMERA_POINTS[0]

  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card/80 shadow-[0_20px_60px_rgba(15,23,42,0.12)]">
      <div className="flex items-center justify-between border-b border-border bg-gradient-to-r from-background/80 via-background/60 to-danger/5 px-4 py-3">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
            <MapPinned className="h-3.5 w-3.5 text-primary" />
            Operations Map
          </div>
          <h3 className="text-sm font-semibold text-foreground">Geo Intelligence Deck</h3>
        </div>
        <Badge variant="outline" className={cn(
          "border px-2 py-1 font-mono text-[10px] uppercase",
          alert ? "border-danger/30 bg-danger/10 text-danger" : "border-success/30 bg-success/10 text-success"
        )}>
          {alert ? `${alert.severity} signal` : "stable"}
        </Badge>
      </div>

      <div className="space-y-4 p-4">
        <div className="relative overflow-hidden rounded-2xl border border-border bg-[radial-gradient(circle_at_top_right,rgba(239,68,68,0.14),transparent_40%),linear-gradient(180deg,rgba(15,23,42,0.96),rgba(15,23,42,0.8))] p-3">
          <div className="absolute inset-0 opacity-40" style={{
            backgroundImage:
              "linear-gradient(rgba(148,163,184,0.10) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.10) 1px, transparent 1px)",
            backgroundSize: "24px 24px",
          }} />

          <div className="absolute left-3 top-3 z-10 rounded-xl border border-white/10 bg-black/35 px-3 py-2 backdrop-blur-sm">
            <p className="text-[10px] uppercase tracking-[0.22em] text-white/50">Focus Zone</p>
            <p className="mt-1 text-sm font-semibold text-white">{alert?.location ?? "Campus Core"}</p>
          </div>

          <div className="absolute right-3 top-3 z-10 rounded-xl border border-white/10 bg-black/35 px-3 py-2 text-right backdrop-blur-sm">
            <p className="text-[10px] uppercase tracking-[0.22em] text-white/50">Active Camera</p>
            <p className="mt-1 text-sm font-semibold text-white">{activeCameraId}</p>
          </div>

          <svg viewBox="0 0 120 96" className="relative z-10 h-56 w-full">
            <defs>
              <linearGradient id="zoneGlow" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="rgba(255,255,255,0.14)" />
                <stop offset="100%" stopColor="rgba(255,255,255,0.04)" />
              </linearGradient>
            </defs>

            <rect x="6" y="6" width="108" height="84" rx="14" fill="url(#zoneGlow)" stroke="rgba(148,163,184,0.20)" />
            <rect x="14" y="14" width="28" height="26" rx="6" fill="rgba(15,23,42,0.65)" stroke="rgba(148,163,184,0.18)" />
            <rect x="44" y="14" width="34" height="14" rx="5" fill="rgba(15,23,42,0.55)" stroke="rgba(148,163,184,0.18)" />
            <rect x="80" y="14" width="22" height="26" rx="6" fill="rgba(15,23,42,0.55)" stroke="rgba(148,163,184,0.18)" />
            <rect x="14" y="42" width="22" height="20" rx="6" fill="rgba(15,23,42,0.55)" stroke="rgba(148,163,184,0.18)" />
            <rect x="38" y="34" width="38" height="28" rx="7" fill="rgba(15,23,42,0.68)" stroke="rgba(148,163,184,0.18)" />
            <rect x="78" y="44" width="24" height="28" rx="6" fill="rgba(15,23,42,0.55)" stroke="rgba(148,163,184,0.18)" />
            <rect x="14" y="64" width="36" height="14" rx="5" fill="rgba(15,23,42,0.48)" stroke="rgba(148,163,184,0.18)" />
            <rect x="52" y="66" width="22" height="12" rx="4" fill="rgba(15,23,42,0.42)" stroke="rgba(148,163,184,0.18)" />

            <path d="M20 50 L100 50" stroke="rgba(148,163,184,0.20)" strokeDasharray="3 4" />
            <path d="M60 20 L60 76" stroke="rgba(148,163,184,0.20)" strokeDasharray="3 4" />

            {CAMERA_POINTS.map((point) => {
              const isActive = point.id === activeCameraId
              const isIncident = alert?.cameraId === point.id
              const isWarm = !isIncident && isActive
              const fill = isIncident ? "#ef4444" : isWarm ? "#f59e0b" : "#22c55e"

              return (
                <g key={point.id}>
                  {isIncident && (
                    <>
                      <circle cx={point.x} cy={point.y} r="8" fill="rgba(239,68,68,0.15)">
                        <animate attributeName="r" values="8;13;8" dur="1.4s" repeatCount="indefinite" />
                      </circle>
                      <circle cx={point.x} cy={point.y} r="4" fill={fill} />
                    </>
                  )}
                  {!isIncident && (
                    <>
                      <circle cx={point.x} cy={point.y} r="5" fill={fill} opacity={isWarm ? 1 : 0.75} />
                      {isWarm && (
                        <circle cx={point.x} cy={point.y} r="9" fill="none" stroke={fill} strokeOpacity="0.35" strokeWidth="1.2">
                          <animate attributeName="r" values="9;13;9" dur="1.8s" repeatCount="indefinite" />
                        </circle>
                      )}
                    </>
                  )}
                  <text x={point.x + 6} y={point.y + 3} fill="rgba(255,255,255,0.82)" fontSize="4.2" fontWeight="600">
                    {point.id}
                  </text>
                  <text x={point.x + 6} y={point.y + 8} fill="rgba(255,255,255,0.48)" fontSize="3.4">
                    {point.label}
                  </text>
                </g>
              )
            })}

            {alert && (
              <g>
                <text x="16" y="88" fill="rgba(248,250,252,0.88)" fontSize="4.6" fontWeight="700">
                  Incident pulse locked on {cameraIndex.label}
                </text>
              </g>
            )}
          </svg>
        </div>

        <div className="grid grid-cols-3 gap-2">
          {CAMERA_POINTS.map((point) => {
            const isActive = point.id === activeCameraId
            const count = alerts.filter((item) => item.cameraId === point.id).length

            return (
              <div
                key={point.id}
                className={cn(
                  "rounded-xl border px-3 py-2 transition-all",
                  isActive ? "border-primary/30 bg-primary/10 shadow-sm" : "border-border bg-background/60"
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
                      <Camera className="h-3 w-3" />
                      Node
                    </div>
                    <p className="mt-1 text-xs font-semibold text-foreground">{point.id}</p>
                  </div>
                  <span className={cn("h-2.5 w-2.5 rounded-full", isActive ? "bg-primary animate-pulse" : "bg-success/80")} />
                </div>
                <p className="mt-2 text-[11px] text-muted-foreground">{point.label}</p>
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{isActive ? "focus" : "live"}</span>
                  <Badge variant="secondary" className="h-5 bg-secondary px-1.5 font-mono text-[10px]">
                    {count}
                  </Badge>
                </div>
              </div>
            )
          })}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-xl border border-danger/20 bg-danger/10 px-3 py-2">
            <div className="flex items-center gap-2 text-danger">
              <ShieldAlert className="h-3.5 w-3.5" />
              <span className="text-[10px] uppercase tracking-[0.22em]">Critical</span>
            </div>
            <p className="mt-1 text-lg font-semibold text-danger">{criticalCount}</p>
          </div>
          <div className="rounded-xl border border-warning/20 bg-warning/10 px-3 py-2">
            <div className="flex items-center gap-2 text-warning">
              <Radar className="h-3.5 w-3.5" />
              <span className="text-[10px] uppercase tracking-[0.22em]">High</span>
            </div>
            <p className="mt-1 text-lg font-semibold text-warning">{highCount}</p>
          </div>
          <div className="rounded-xl border border-border bg-background/70 px-3 py-2">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Activity className="h-3.5 w-3.5" />
              <span className="text-[10px] uppercase tracking-[0.22em]">Fusion</span>
            </div>
            <p className="mt-1 text-lg font-semibold text-foreground">{alert?.fusionScore?.toFixed(1) ?? "--"}</p>
          </div>
          <div className="rounded-xl border border-border bg-background/70 px-3 py-2">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5" />
              <span className="text-[10px] uppercase tracking-[0.22em]">Signal</span>
            </div>
            <p className="mt-1 text-lg font-semibold text-foreground">{alert ? "Hot" : "Clear"}</p>
          </div>
        </div>

        {alert && (
          <div className="rounded-xl border border-border bg-background/70 px-3 py-2">
            <p className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground">Fusion rationale</p>
            <p className="mt-1 text-xs text-foreground/80">{alert.fusionReason ?? "Fusion score combined violence and motion cues."}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Badge variant="secondary" className="h-5 bg-secondary px-1.5 font-mono text-[10px]">
                Motion {alert.motionScore?.toFixed(1) ?? "--"}%
              </Badge>

              <Badge variant="secondary" className="h-5 bg-secondary px-1.5 font-mono text-[10px]">
                Model {alert.fusionModel ?? "fusion-v1"}
              </Badge>
            </div>
          </div>
        )}
      </div>
    </section>
  )
})
