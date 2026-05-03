"use client"

import React, { useCallback } from "react"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Badge } from "@/components/ui/badge"
import { DetectionCategory, CATEGORY_LABELS, CATEGORY_COLORS } from "@/lib/detection-types"
import { Filter } from "lucide-react"

interface CategoryFilterProps {
  selectedCategories: DetectionCategory[]
  onCategoryChange: (categories: DetectionCategory[]) => void
  categoryCounts?: Partial<Record<DetectionCategory, number>>
}

export function CategoryFilter({ 
  selectedCategories, 
  onCategoryChange,
  categoryCounts = {},
}: CategoryFilterProps) {
  const allCategories: DetectionCategory[] = [
    "violence",
    "weapon", 
    "crowd_surge",
    "fall",
    "intrusion",
    "loitering",
  ]

  const handleToggle = useCallback(
    (value: string[]) => {
      const categories = value as DetectionCategory[]
      onCategoryChange(categories)
    },
    [onCategoryChange],
  )

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
        {allCategories.map((cat) => {
          const count = categoryCounts[cat] || 0
          const isSelected = selectedCategories.includes(cat)
          
          return (
            <ToggleGroupItem
              key={cat}
              value={cat}
              size="sm"
              className={`text-xs ${isSelected ? CATEGORY_COLORS[cat] : ""}`}
            >
              {CATEGORY_LABELS[cat]}
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
