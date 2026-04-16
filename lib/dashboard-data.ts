export interface Alert {
  id: string
  timestamp: string
  cameraId: string
  cameraLocation: string
  type: "Fighting" | "Weapon" | "Panic" | "Vandalism" | "Intrusion"
  confidence: number
  severity: "critical" | "high" | "medium"
  description: string
  location: string
  timeAgo: string
  detectedAction: string
}

export const alerts: Alert[] = [
  {
    id: "ALT-001",
    timestamp: "14:32:05",
    cameraId: "CAM-04",
    cameraLocation: "Hallway B",
    type: "Fighting",
    confidence: 96,
    severity: "critical",
    description: "Physical assault detected - two individuals engaged in punching.",
    location: "North Gate Entrance",
    timeAgo: "2 mins ago",
    detectedAction: "Physical Assault (Punching)",
  },
  {
    id: "ALT-002",
    timestamp: "14:28:41",
    cameraId: "CAM-12",
    cameraLocation: "Parking Lot A",
    type: "Weapon",
    confidence: 89,
    severity: "critical",
    description: "Potential weapon detected in hand of unidentified individual.",
    location: "Parking Lot A - Section 3",
    timeAgo: "5 mins ago",
    detectedAction: "Weapon Possession (Blunt Object)",
  },
  {
    id: "ALT-003",
    timestamp: "14:15:22",
    cameraId: "CAM-07",
    cameraLocation: "Main Lobby",
    type: "Panic",
    confidence: 78,
    severity: "high",
    description: "Crowd panic behavior detected - rapid dispersal pattern.",
    location: "Main Lobby - East Wing",
    timeAgo: "18 mins ago",
    detectedAction: "Crowd Panic (Rapid Dispersal)",
  },
  {
    id: "ALT-004",
    timestamp: "13:52:10",
    cameraId: "CAM-02",
    cameraLocation: "Stairwell C",
    type: "Fighting",
    confidence: 92,
    severity: "high",
    description: "Aggressive physical confrontation between three individuals.",
    location: "Stairwell C - Floor 2",
    timeAgo: "42 mins ago",
    detectedAction: "Group Altercation (3 Persons)",
  },
  {
    id: "ALT-005",
    timestamp: "13:30:55",
    cameraId: "CAM-15",
    cameraLocation: "Loading Dock",
    type: "Vandalism",
    confidence: 85,
    severity: "medium",
    description: "Deliberate property damage detected at loading dock entrance.",
    location: "Loading Dock - Bay 2",
    timeAgo: "1 hr ago",
    detectedAction: "Property Damage (Kicking)",
  },
  {
    id: "ALT-006",
    timestamp: "12:45:33",
    cameraId: "CAM-09",
    cameraLocation: "Perimeter East",
    type: "Intrusion",
    confidence: 74,
    severity: "medium",
    description: "Unauthorized individual detected climbing perimeter fence.",
    location: "East Perimeter - Sector 4",
    timeAgo: "1 hr 48 mins ago",
    detectedAction: "Fence Breach Attempt",
  },
  {
    id: "ALT-007",
    timestamp: "12:10:18",
    cameraId: "CAM-21",
    cameraLocation: "Cafeteria",
    type: "Fighting",
    confidence: 81,
    severity: "high",
    description: "Verbal altercation escalated to physical contact.",
    location: "Cafeteria - Area B",
    timeAgo: "2 hrs 23 mins ago",
    detectedAction: "Physical Confrontation (Shoving)",
  },
]

export const floorPlanRooms = [
  { id: "lobby", label: "Main Lobby", x: 20, y: 15, w: 30, h: 20 },
  { id: "hallway-b", label: "Hallway B", x: 55, y: 15, w: 25, h: 12 },
  { id: "stairwell-c", label: "Stairwell C", x: 82, y: 10, w: 12, h: 18 },
  { id: "cafeteria", label: "Cafeteria", x: 20, y: 42, w: 35, h: 25 },
  { id: "parking-a", label: "Parking A", x: 60, y: 35, w: 30, h: 20 },
  { id: "loading-dock", label: "Loading Dock", x: 60, y: 60, w: 25, h: 15 },
  { id: "perimeter-east", label: "East Perimeter", x: 88, y: 35, w: 8, h: 45 },
  { id: "north-gate", label: "North Gate", x: 35, y: 2, w: 15, h: 10 },
]

export const cameraLocations: Record<string, { roomId: string; x: number; y: number }> = {
  "CAM-04": { roomId: "hallway-b", x: 65, y: 20 },
  "CAM-12": { roomId: "parking-a", x: 75, y: 45 },
  "CAM-07": { roomId: "lobby", x: 35, y: 25 },
  "CAM-02": { roomId: "stairwell-c", x: 88, y: 18 },
  "CAM-15": { roomId: "loading-dock", x: 72, y: 67 },
  "CAM-09": { roomId: "perimeter-east", x: 92, y: 55 },
  "CAM-21": { roomId: "cafeteria", x: 37, y: 54 },
}
