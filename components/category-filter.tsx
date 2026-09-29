"use client"

import { useEffect, useState } from "react"
import { Crosshair, Filter, ShieldAlert } from "lucide-react"
import { apiFetch } from "@/lib/api-auth"
import { useSentinel } from "@/lib/sentinel-store"
import { CATEGORY_LABELS, type CategoryStatus, type DetectionCategory } from "@/lib/detection-types"

interface CategoryFilterProps {
  selectedCategories: DetectionCategory[]
  onCategoryChange: (categories: DetectionCategory[]) => void
  categoryCounts?: Partial<Record<DetectionCategory, number>>
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"
const TYPES = ["weapon", "violence"] as const
const SEVERITIES = [
  { id: "critical", label: "حرج", color: "var(--threat-critical)" },
  { id: "high", label: "مرتفع", color: "var(--threat-high)" },
  { id: "medium", label: "متوسط", color: "var(--threat-medium)" },
] as const
type Capability = { id: typeof TYPES[number]; status: CategoryStatus; reason?: string }

export function CategoryFilter({ selectedCategories, onCategoryChange, categoryCounts = {} }: CategoryFilterProps) {
  const { filters, setFilters, connectionStatus, fixtureMode } = useSentinel()
  const [capabilities, setCapabilities] = useState<Capability[]>([])

  useEffect(() => {
    if (fixtureMode || connectionStatus !== "online") return
    const controller = new AbortController()
    apiFetch(`${API_BASE}/api/categories`, { signal: controller.signal })
      .then((response) => response.ok ? response.json() : null)
      .then((data: { categories?: unknown } | null) => {
        if (Array.isArray(data?.categories)) {
          setCapabilities(data.categories.flatMap((value): Capability[] => {
            if (value === null || typeof value !== "object" ||
              !("id" in value) || !TYPES.includes(value.id as typeof TYPES[number]) ||
              !("status" in value) || !["active", "experimental", "unsupported"].includes(String(value.status))) return []
            return [{ id: value.id as Capability["id"], status: value.status as CategoryStatus,
              reason: "reason" in value && typeof value.reason === "string" ? value.reason : undefined }]
          }))
        }
      })
      .catch(() => { /* Capability details are optional when the backend is offline. */ })
    return () => controller.abort()
  }, [connectionStatus, fixtureMode])

  return <div className="sticky top-0 z-10 border-b border-[var(--border-hairline)] bg-[var(--surface-1)] px-3 py-3">
    <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold text-[var(--text-secondary)]"><Filter size={13} />تصفية التنبيهات</div>
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="نوع التنبيه">
      <button type="button" aria-pressed={selectedCategories.length === 0} onClick={() => onCategoryChange([])} className={`min-h-8 rounded border px-2.5 text-[11px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)] ${selectedCategories.length === 0 ? "border-[var(--signal)] bg-[var(--surface-3)] text-[var(--signal)]" : "border-[var(--border-hairline)] text-[var(--text-secondary)] hover:bg-[var(--surface-2)]"}`}>الكل</button>
      {TYPES.map((category) => {
        const selected = selectedCategories.includes(category)
        const capability = connectionStatus === "online" && !fixtureMode ? capabilities.find((item) => item.id === category) : undefined
        const Icon = category === "weapon" ? Crosshair : ShieldAlert
        const color = category === "weapon" ? "var(--cat-weapon)" : "var(--cat-violence)"
        return <button key={category} type="button" aria-pressed={selected} onClick={() => onCategoryChange(selected ? [] : [category])} title={capability?.reason || undefined} className="flex min-h-8 items-center gap-1.5 rounded border px-2.5 text-[11px] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)]" style={{ color: selected ? color : "var(--text-secondary)", borderColor: selected ? color : "var(--border-hairline)", background: selected ? "var(--surface-3)" : undefined }}>
          <Icon size={12} />{CATEGORY_LABELS[category]}
          {categoryCounts[category] !== undefined && <bdi className="instrument-num text-[10px]">{categoryCounts[category]}</bdi>}
          {capability?.status === "experimental" && <span className="text-[9px]">تجريبي</span>}
          {capability?.status === "unsupported" && <span className="text-[9px]">غير مدعوم حالياً</span>}
        </button>
      })}
    </div>
    <div className="mt-2 flex flex-wrap items-center gap-1.5" role="group" aria-label="درجة الخطورة">
      <span className="me-1 text-[10px] text-[var(--text-tertiary)]">الخطورة</span>
      {SEVERITIES.map(({ id, label, color }) => <button key={id} type="button" aria-pressed={filters.severity === id} onClick={() => setFilters({ ...filters, severity: filters.severity === id ? undefined : id })} className="min-h-7 rounded border px-2 text-[10px] hover:bg-[var(--surface-2)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--signal)]" style={{ color: filters.severity === id ? color : "var(--text-secondary)", borderColor: filters.severity === id ? color : "var(--border-hairline)", background: filters.severity === id ? "var(--surface-3)" : undefined }}>{label}</button>)}
    </div>
  </div>
}
