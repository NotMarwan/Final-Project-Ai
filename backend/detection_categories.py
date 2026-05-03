from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Mapping, Union
import numpy as np


@dataclass(frozen=True)
class Box:
    x1: float
    y1: float
    x2: float
    y2: float
    label: str = "person"
    score: float = 1.0
    track_id: Optional[str] = None


@dataclass(frozen=True)
class Zone:
    id: str
    camera_id: Optional[str]
    x1: float
    y1: float
    x2: float
    y2: float
    label: str = "restricted"


@dataclass(frozen=True)
class DetectionContext:
    frame: Optional[np.ndarray] = None
    camera_id: Optional[str] = None
    timestamp: Optional[float] = None
    base_confidence: float = 0.0
    person_boxes: List[Box] = field(default_factory=list)
    restricted_zones: List[Zone] = field(default_factory=list)


class DetectionCategory(str, Enum):
    VIOLENCE = "violence"
    WEAPON = "weapon"
    CROWD_SURGE = "crowd_surge"
    FALL = "fall"
    INTRUSION = "intrusion"
    LOITERING = "loitering"


class CategoryStatus(str, Enum):
    ACTIVE = "active"
    EXPERIMENTAL = "experimental"
    UNSUPPORTED = "unsupported"


@dataclass
class CategoryConfig:
    violence_enabled: bool = True
    violence_threshold: float = 0.5
    weapon_enabled: bool = False
    weapon_threshold: float = 0.55
    crowd_surge_enabled: bool = False
    crowd_surge_threshold: float = 0.70
    fall_enabled: bool = False
    fall_threshold: float = 0.65
    intrusion_enabled: bool = False
    intrusion_threshold: float = 0.60
    intrusion_weight: float = 0.75
    loitering_enabled: bool = False
    loitering_threshold: float = 0.60

    @classmethod
    def from_settings(cls, settings: Optional[Dict[str, Any]] = None) -> "CategoryConfig":
        settings = settings or {}
        return cls(
            violence_enabled=settings.get("violence_enabled", True),
            violence_threshold=settings.get("violence_threshold", 0.5),
            weapon_enabled=settings.get("weapon_enabled", False),
            weapon_threshold=settings.get("weapon_threshold", 0.55),
            crowd_surge_enabled=settings.get("crowd_surge_enabled", False),
            crowd_surge_threshold=settings.get("crowd_surge_threshold", 0.70),
            fall_enabled=settings.get("fall_enabled", False),
            fall_threshold=settings.get("fall_threshold", 0.65),
            intrusion_enabled=settings.get("intrusion_enabled", False),
            intrusion_threshold=settings.get("intrusion_threshold", 0.60),
            intrusion_weight=settings.get("intrusion_weight", 0.75),
            loitering_enabled=settings.get("loitering_enabled", False),
            loitering_threshold=settings.get("loitering_threshold", 0.60),
        )


class CategoryDetector:
    def __init__(self, config: CategoryConfig, weapon_engine: Optional[Any] = None):
        self.config = config
        self.weapon_engine = weapon_engine
        self._enabled_categories: List[DetectionCategory] = [
            cat for cat in DetectionCategory
            if getattr(config, f"{cat.value}_enabled", False)
        ]

    @property
    def enabled_categories(self) -> List[DetectionCategory]:
        return self._enabled_categories

    def is_category_enabled(self, category: DetectionCategory) -> bool:
        return category in self._enabled_categories

    def get_capability(self, category: DetectionCategory, context: Optional[DetectionContext] = None) -> Dict[str, Any]:
        """Return the capability status for a category."""
        base = {
            "id": category.value,
            "label": category.name.replace("_", " ").title(),
            "enabled": self.is_category_enabled(category),
            "threshold": getattr(self.config, f"{category.value}_threshold", 0.0),
            "status": CategoryStatus.UNSUPPORTED.value,
            "reason": "Not implemented",
            "requiredInputs": [],
        }

        if category == DetectionCategory.VIOLENCE:
            base.update({
                "status": CategoryStatus.ACTIVE.value,
                "reason": "Connected to active X3D temporal engine.",
                "requiredInputs": ["frame"]
            })
        elif category == DetectionCategory.WEAPON:
            if self.weapon_engine is None:
                base.update({
                    "enabled": False,
                    "status": CategoryStatus.UNSUPPORTED.value,
                    "reason": "Weapon detection engine not initialized."
                })
            else:
                signal = self.weapon_engine.latest_signal()
                is_realtime = signal.get("isRealtime", False)
                reason = "Weapon bridge connected."
                if not is_realtime and signal.get("ready"):
                    latency = signal.get("inferenceLatencyMs", 0)
                    reason = f"CPU inference is slow (~{latency:.0f}ms); running with backpressure."
                
                base.update({
                    "enabled": self.config.weapon_enabled and signal.get("ready", False),
                    "status": CategoryStatus.EXPERIMENTAL.value,
                    "reason": reason,
                    "requiredInputs": ["frame"]
                })
        elif category == DetectionCategory.INTRUSION:
            # Intrusion is only supported if we have zones AND person boxes in context
            has_zones = context and len(context.restricted_zones) > 0
            has_persons = context and len(context.person_boxes) > 0
            
            if not has_zones or not has_persons:
                reasons = []
                if not has_zones: reasons.append("restricted zones")
                if not has_persons: reasons.append("person boxes")
                
                base.update({
                    "enabled": False,
                    "status": CategoryStatus.UNSUPPORTED.value,
                    "reason": f"Requires {', '.join(reasons)}.",
                    "requiredInputs": ["person_boxes", "restricted_zones", "camera_id"]
                })
            else:
                base.update({
                    "status": CategoryStatus.EXPERIMENTAL.value,
                    "reason": "Zone-based analysis active.",
                    "requiredInputs": ["person_boxes", "restricted_zones", "camera_id"]
                })
        else:
            base.update({
                "reason": "Implementation pending Phase 4/5 enhancements.",
                "requiredInputs": ["frame"]
            })

        return base

    def get_all_capabilities(self, context: Optional[DetectionContext] = None) -> List[Dict[str, Any]]:
        return [self.get_capability(cat, context) for cat in DetectionCategory]

    def analyze_frame(self, frame: np.ndarray, category: DetectionCategory, base_confidence: float = 0.0) -> Dict[DetectionCategory, float]:
        """Backward compatibility for simple frame-based calls."""
        ctx = DetectionContext(frame=frame, base_confidence=base_confidence)
        return self.analyze_context(ctx, category)

    def analyze_context(self, context: DetectionContext, category: DetectionCategory) -> Dict[DetectionCategory, float]:
        """Primary entry point for context-aware analysis."""
        scores = {category: 0.0}
        
        # Guard: check capability first
        cap = self.get_capability(category, context)
        if cap["status"] == CategoryStatus.UNSUPPORTED.value:
            return scores
            
        # Also check if enabled
        if not self.is_category_enabled(category):
            return scores

        if category == DetectionCategory.VIOLENCE:
            scores[category] = context.base_confidence
        elif category == DetectionCategory.WEAPON:
            if self.weapon_engine and context.frame is not None:
                try:
                    res = self.weapon_engine.process_frame(context.frame)
                    scores[category] = res.get("score", 0.0)
                except Exception:
                    scores[category] = 0.0
        elif category == DetectionCategory.INTRUSION:
            scores[category] = self._detect_intrusion(context)
        elif category == DetectionCategory.CROWD_SURGE:
            scores[category] = self._detect_crowd_surge(context.frame)
        elif category == DetectionCategory.FALL:
            scores[category] = self._detect_fall(context.frame)
        elif category == DetectionCategory.LOITERING:
            scores[category] = self._detect_loitering(context.frame)

        return scores

    def _detect_intrusion(self, context: DetectionContext) -> float:
        """Detect intrusion using zone overlap logic."""
        if not context.person_boxes or not context.restricted_zones:
            return 0.0
            
        max_overlap = 0.0
        for person in context.person_boxes:
            for zone in context.restricted_zones:
                # Optional camera_id matching
                if zone.camera_id and context.camera_id and zone.camera_id != context.camera_id:
                    continue
                    
                overlap = self._box_overlap_ratio(person, zone)
                if overlap > max_overlap:
                    max_overlap = overlap
                    
        return float(max_overlap)

    def _box_overlap_ratio(self, person: Box, zone: Zone) -> float:
        """Compute how much of the person box is inside the zone."""
        # Intersection
        ix1 = max(person.x1, zone.x1)
        iy1 = max(person.y1, zone.y1)
        ix2 = min(person.x2, zone.x2)
        iy2 = min(person.y2, zone.y2)
        
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
            
        intersection_area = (ix2 - ix1) * (iy2 - iy1)
        person_area = (person.x2 - person.x1) * (person.y2 - person.y1)
        
        if person_area <= 0:
            return 0.0
            
        return intersection_area / person_area

    def _detect_crowd_surge(self, frame: Optional[np.ndarray]) -> float:
        return 0.0

    def _detect_fall(self, frame: Optional[np.ndarray]) -> float:
        return 0.0

    def _detect_loitering(self, frame: Optional[np.ndarray]) -> float:
        return 0.0

    def get_category_severity(self, category: DetectionCategory) -> str:
        """Get the default severity level for a category."""
        severity_map = {
            DetectionCategory.VIOLENCE: "high",
            DetectionCategory.WEAPON: "critical",
            DetectionCategory.CROWD_SURGE: "medium",
            DetectionCategory.FALL: "high",
            DetectionCategory.INTRUSION: "medium",
            DetectionCategory.LOITERING: "low",
        }
        return severity_map.get(category, "medium")

