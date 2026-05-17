import type { MultiThreatData, ThreatBox } from "@/lib/detection-types"

export interface ModelOutput {
  model: "x3d" | "visafe" | "yolov8" | "yolo26" | "rtdetr"
  violenceScore: number
  weaponScore: number
  violenceBbox: [number, number, number, number] | null
  weaponBbox: [number, number, number, number] | null
  weaponType: "gun" | "knife" | "explosive" | "unknown" | null
  weaponLabels: string[]
  fusedScore: number
  severity: "low" | "medium" | "high" | "critical"
}

const WEAPON_COLOR_MAP: Record<string, [number, number, number]> = {
  gun: [220, 38, 38],
  knife: [245, 158, 11],
  explosive: [239, 68, 68],
  unknown: [234, 179, 8],
}

const WEAPON_TYPE_KEYWORDS: Record<string, string[]> = {
  gun: ["gun", "pistol", "rifle", "revolver", "shotgun"],
  knife: ["knife", "blade", "sword", "dagger"],
  explosive: ["bomb", "grenade", "explosive", "dynamite"],
}

function classifyWeapon(labels: string[]): "gun" | "knife" | "explosive" | "unknown" {
  const lower = labels.map(l => l.toLowerCase())
  for (const [type, keywords] of Object.entries(WEAPON_TYPE_KEYWORDS)) {
    if (lower.some(l => keywords.some(k => l.includes(k)))) {
      return type as "gun" | "knife" | "explosive"
    }
  }
  return "unknown"
}

export function normalizeToMultiThreat(output: ModelOutput): MultiThreatData {
  const hasViolence = output.violenceScore >= 50
  const hasWeapon = output.weaponScore >= 55
  const isMultiThreat = hasViolence && hasWeapon

  const threatBoxes: ThreatBox[] = []

  if (hasViolence && output.violenceBbox) {
    threatBoxes.push({
      id: "violence-01",
      type: "violence",
      bbox: output.violenceBbox,
      confidence: output.violenceScore / 100,
      color: [239, 68, 68],
      label: "VIOLENCE",
    })
  }

  if (hasWeapon && output.weaponBbox) {
    const wType = output.weaponType ?? classifyWeapon(output.weaponLabels)
    threatBoxes.push({
      id: "weapon-" + wType,
      type: "weapon",
      weaponType: wType,
      bbox: output.weaponBbox,
      confidence: output.weaponScore / 100,
      color: WEAPON_COLOR_MAP[wType] ?? WEAPON_COLOR_MAP.unknown,
      label: wType.toUpperCase() !== "UNKNOWN" ? wType.toUpperCase() : "WEAPON",
    })
  }

  return {
    hasViolence,
    hasWeapon,
    isMultiThreat,
    violenceScore: output.violenceScore,
    weaponScore: output.weaponScore,
    fusedScore: output.fusedScore,
    severity: output.severity,
    threatBoxes,
    reason: "",
  }
}