// AI-Sentinel Detection Types (Phase 1 - Minimal Additive Implementation)
// These types mirror the backend detection_schema.py structures

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type DetectorSource = "weapon_engine" | "yolo" | "manual/demo" | "future_model";

export interface DetectionObject {
  id: string;
  label: string;
  class_name: string;
  confidence: number;
  bbox?: [number, number, number, number]; // [x, y, width, height] in pixels
  normalized_bbox?: [number, number, number, number]; // [x, y, width, height] normalized 0-1
  risk_level: RiskLevel;
  source: DetectorSource;
  timestamp: string; // ISO 8601 format
}

// Helper type for alert payload with detections
export interface AlertPayloadWithDetections {
  // ... existing alert fields ...
  detections: DetectionObject[];
  danger_alert: boolean;
  risk_level: string;
  detectionCount: number;
  weapon_detections: DetectionObject[];
  danger_detections: DetectionObject[];
}
