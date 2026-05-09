from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any, List

class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class DetectorSource(Enum):
    WEAPON_ENGINE = "weapon_engine"
    YOLO = "yolo"
    MANUAL_DEMO = "manual/demo"
    FUTURE_MODEL = "future_model"

@dataclass
class DetectionObject:
    id: str
    label: str
    class_name: str
    confidence: float
    risk_level: RiskLevel
    source: DetectorSource
    timestamp: str
    bbox: Optional[List[float]] = None
    normalized_bbox: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert DetectionObject to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "label": self.label,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": self.bbox,
            "normalized_bbox": self.normalized_bbox,
            "risk_level": self.risk_level.value,
            "source": self.source.value,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DetectionObject':
        """Create a DetectionObject from a dictionary."""
        return cls(
            id=data["id"],
            label=data["label"],
            class_name=data["class_name"],
            confidence=data["confidence"],
            risk_level=RiskLevel(data["risk_level"]),
            source=DetectorSource(data["source"]),
            timestamp=data["timestamp"],
            bbox=data.get("bbox"),
            normalized_bbox=data.get("normalized_bbox")
        )
