export type DetectionCategory = 
  | "violence"
  | "weapon"
  | "crowd_surge"
  | "fall"
  | "intrusion"
  | "loitering"

export interface CategoryConfig {
  violenceEnabled: boolean
  violenceThreshold: number
  weaponEnabled: boolean
  weaponThreshold: number
  crowdSurgeEnabled: boolean
  crowdSurgeThreshold: number
  fallEnabled: boolean
  fallThreshold: number
  intrusionEnabled: boolean
  intrusionThreshold: number
  loiteringEnabled: boolean
  loiteringThreshold: number
}

export interface CategoryScore {
  category: DetectionCategory
  score: number
  threshold: number
  triggered: boolean
  severity: "low" | "medium" | "high" | "critical"
}

export const CATEGORY_LABELS: Record<DetectionCategory, string> = {
  violence: "Violence",
  weapon: "Weapon", // Note: Weapon detection is partially handled by weapon.py
  crowd_surge: "Crowd Surge",
  fall: "Fall Detection (Placeholder)",
  intrusion: "Intrusion (Placeholder)",
  loitering: "Loitering (Placeholder)",
}

export const CATEGORY_COLORS: Record<DetectionCategory, string> = {
  violence: "text-red-500 bg-red-500/10 border-red-500/20",
  weapon: "text-orange-500 bg-orange-500/10 border-orange-500/20",
  crowd_surge: "text-yellow-500 bg-yellow-500/10 border-yellow-500/20",
  fall: "text-blue-500 bg-blue-500/10 border-blue-500/20",
  intrusion: "text-purple-500 bg-purple-500/10 border-purple-500/20",
  loitering: "text-gray-500 bg-gray-500/10 border-gray-500/20",
}

export const CATEGORY_ICONS: Record<DetectionCategory, string> = {
  violence: "AlertTriangle",
  weapon: "Crosshair",
  crowd_surge: "Users",
  fall: "ArrowDown",
  intrusion: "ShieldAlert",
  loitering: "Clock",
}
