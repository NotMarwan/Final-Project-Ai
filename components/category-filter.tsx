"use client"

import React, { useCallback, useEffect, useState } from "react"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Badge } from "@/components/ui/badge"
import { DetectionCategory, CATEGORY_LABELS, CATEGORY_COLORS, CategoryCapability } from "@/lib/detection-types"
import { Filter } from "lucide-react"

interface CategoryFilterProps {
  selectedCategories: DetectionCategory[]
  onCategoryChange: (categories: DetectionCategory[]) => void
  categoryCounts?: Partial<Record<DetectionCategory, number>>
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8002"

export function CategoryFilter({ 
  selectedCategories, 
  onCategoryChange,
  categoryCounts = {},
}: CategoryFilterProps) {
  const [capabilities, setCapabilities] = useState<CategoryCapability[]>([])

  useEffect(() => {
    fetch(`${API_BASE}/api/categories`)
      .then(res => res.json())
      .then(data => {
        if (data.categories) {
          setCapabilities(data.categories)
        }
      })
      .catch(console.error)
  }, [])

  const handleToggle = useCallback(
    (value: string[]) => {
      const categories = value as DetectionCategory[]
      onCategoryChange(categories)
    },
    [onCategoryChange],
  )

  // Use capabilities from backend if available, otherwise fallback to default list
  const displayCategories = capabilities.length > 0 
    ? capabilities 
    : [
        { id: "violence", status: "active" } as CategoryCapability,
        { id: "weapon", status: "experimental" } as CategoryCapability,
      ]

  return (
    <div className="flex items-center gap-2 p-2 border-b border-border">
      <Filter className="h-4 w-4 text-muted-foreground" />
      <span className="text-sm text-muted-foreground mr-2">Filter:</span>
      
      <ToggleGroup
        type="multiple"
        value={selectedCategories}
        onValueChange={handleToggle}
        className="flex-wrap"
      >
        {displayCategories.map((cap) => {
          const cat = cap.id
          const count = categoryCounts[cat] || 0
          const isSelected = selectedCategories.includes(cat)
          const isUnsupported = cap.status === "unsupported"
          
          if (isUnsupported) return null; // Hide unsupported categories

          return (
            <ToggleGroupItem
              key={cat}
              value={cat}
              size="sm"
              disabled={isUnsupported}
              className={`text-xs ${isSelected ? CATEGORY_COLORS[cat] : ""}`}
              title={cap.reason || CATEGORY_LABELS[cat]}
            >
              {CATEGORY_LABELS[cat]}
              {cap.status === "experimental" && (
                <span className="ml-1 text-[9px] text-muted-foreground">(Exp)</span>
              )}
              {count > 0 && (
                <Badge variant="secondary" className="ml-1 h-4 px-1 text-[10px]">
                  {count}
                </Badge>
              )}
            </ToggleGroupItem>
          )
        })}
      </ToggleGroup>
    </div>
  )
}
