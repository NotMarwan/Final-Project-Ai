"use client"

import { useState, useEffect, useCallback } from "react"
import { Send, CheckCircle, XCircle, AlertCircle, Clock, MessageSquare } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

interface TelegramStatus {
  enabled: boolean
  configured: boolean
  lastSendStatus: string | null
  lastError: string | null
  lastSentAt: string | null
  minAlertIntervalSeconds: number
  provider: string
  running: boolean
  min_severity: string
}

interface TelegramStatusCardProps {
  /** Optional: pass the status directly if parent already has it */
  status?: TelegramStatus
  /** Whether the current user has admin role to see the test button */
  isAdmin?: boolean
}

export function TelegramStatusCard({ status: propStatus, isAdmin = false }: TelegramStatusCardProps) {
  const [status, setStatus] = useState<TelegramStatus | null>(propStatus ?? null)
  const [loading, setLoading] = useState(!propStatus)
  const [testLoading, setTestLoading] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/system/status`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (data.notifications) {
        setStatus(data.notifications as TelegramStatus)
      }
    } catch (err) {
      console.error("Failed to fetch Telegram status:", err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!propStatus) {
      fetchStatus()
      const interval = setInterval(fetchStatus, 30_000) // Refresh every 30s
      return () => clearInterval(interval)
    }
  }, [propStatus, fetchStatus])

  const handleTest = async () => {
    setTestLoading(true)
    setTestResult(null)
    try {
      const res = await fetch(`${API_BASE}/notifications/telegram/test`, {
        method: "POST",
      })
      const data = await res.json().catch(() => ({}))
      if (res.ok && data.success) {
        setTestResult({ success: true, message: "Test message sent successfully" })
        // Refresh status after test
        setTimeout(fetchStatus, 1000)
      } else {
        setTestResult({
          success: false,
          message: data.error ?? data.detail ?? `HTTP ${res.status}`,
        })
      }
    } catch (err) {
      setTestResult({
        success: false,
        message: err instanceof Error ? err.message : "Network error",
      })
    } finally {
      setTestLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-card/50 p-4">
        <div className="flex items-center gap-2 text-muted-foreground">
          <MessageSquare className="h-4 w-4 animate-pulse" />
          <span className="text-sm">Loading Telegram status...</span>
        </div>
      </div>
    )
  }

  if (!status) {
    return null
  }

  const getStatusVariant = (): "success" | "danger" | "warning" => {
    if (!status.enabled) return "warning"
    if (!status.configured) return "danger"
    if (status.lastSendStatus === "failed") return "danger"
    if (status.lastSendStatus === "success") return "success"
    return "warning"
  }

  const getStatusLabel = (): string => {
    if (!status.enabled) return "Disabled"
    if (!status.configured) return "Not Configured"
    if (status.running) return "Active"
    return "Stopped"
  }

  const variant = getStatusVariant()
  const statusLabel = getStatusLabel()

  const variantStyles = {
    success: "border-success/30 bg-success/5 text-success",
    danger: "border-danger/30 bg-danger/5 text-danger",
    warning: "border-warning/30 bg-warning/5 text-warning",
  }

  const dotStyles = {
    success: "bg-success",
    danger: "bg-danger animate-pulse",
    warning: "bg-warning",
  }

  return (
    <div className={cn("rounded-lg border p-4 space-y-3", variantStyles[variant])}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          <span className="text-sm font-semibold">Telegram Notifications</span>
        </div>
        <Badge variant={variant === "success" ? "default" : "secondary"} className="text-xs">
          <span className={cn("mr-1.5 inline-block h-1.5 w-1.5 rounded-full", dotStyles[variant])} />
          {statusLabel}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex items-center gap-1.5">
          {status.configured ? (
            <CheckCircle className="h-3 w-3 text-success" />
          ) : (
            <XCircle className="h-3 w-3 text-danger" />
          )}
          <span className="text-muted-foreground">
            {status.configured ? "Configured" : "Not Configured"}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          {status.enabled ? (
            <CheckCircle className="h-3 w-3 text-success" />
          ) : (
            <XCircle className="h-3 w-3 text-muted-foreground" />
          )}
          <span className="text-muted-foreground">
            {status.enabled ? "Enabled" : "Disabled"}
          </span>
        </div>

        {status.lastSendStatus && (
          <div className="flex items-center gap-1.5">
            {status.lastSendStatus === "success" ? (
              <CheckCircle className="h-3 w-3 text-success" />
            ) : status.lastSendStatus === "cooldown" ? (
              <Clock className="h-3 w-3 text-warning" />
            ) : (
              <AlertCircle className="h-3 w-3 text-danger" />
            )}
            <span className="text-muted-foreground">
              Last: {status.lastSendStatus}
            </span>
          </div>
        )}

        {status.lastSentAt && (
          <div className="flex items-center gap-1.5">
            <Clock className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">
              Sent: {new Date(status.lastSentAt).toLocaleTimeString()}
            </span>
          </div>
        )}
      </div>

      {status.lastError && (
        <div className="rounded bg-danger/10 p-2 text-xs text-danger">
          <AlertCircle className="inline h-3 w-3 mr-1" />
          {status.lastError}
        </div>
      )}

      {testResult && (
        <div
          className={cn(
            "rounded p-2 text-xs",
            testResult.success ? "bg-success/10 text-success" : "bg-danger/10 text-danger"
          )}
        >
          {testResult.success ? (
            <CheckCircle className="inline h-3 w-3 mr-1" />
          ) : (
            <XCircle className="inline h-3 w-3 mr-1" />
          )}
          {testResult.message}
        </div>
      )}

      {isAdmin && status.configured && (
        <Button
          size="sm"
          variant="outline"
          className="w-full text-xs"
          onClick={handleTest}
          disabled={testLoading}
        >
          <Send className="mr-1.5 h-3 w-3" />
          {testLoading ? "Sending..." : "Send Test Message"}
        </Button>
      )}
    </div>
  )
}
