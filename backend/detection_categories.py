"""
Detection Categories System
Expands beyond violence to: weapon, crowd_surge, fall, intrusion, loitering
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import numpy as np


class DetectionCategory(str, Enum):
    """Supported detection categories."""
    VIOLENCE = "violence"
    WEAPON = "weapon"
    CROWD_SURGE = "crowd_surge"
    FALL = "fall"
    INTRUSION = "intrusion"
    LOITERING = "loitering"


@dataclass(frozen=True)
class CategoryConfig:
    """Configuration for each detection category."""
    violence_enabled: bool = True
    violence_threshold: float = 0.75
    violence_weight: float = 1.0
    
    weapon_enabled: bool = False
    weapon_threshold: float = 0.55
    weapon_weight: float = 0.9
    
    crowd_surge_enabled: bool = False
    crowd_surge_threshold: float = 0.70
    crowd_surge_weight: float = 0.8
    
    fall_enabled: bool = False
    fall_threshold: float = 0.65
    fall_weight: float = 0.85
    
    intrusion_enabled: bool = False
    intrusion_threshold: float = 0.60
    intrusion_weight: float = 0.75
    
    loitering_enabled: bool = False
    loitering_threshold: float = 0.50
    loitering_weight: float = 0.6
    
    @classmethod
    def from_settings(cls, settings: Optional[Dict[str, Any]] = None) -> "CategoryConfig":
        settings = settings or {}
        return cls(
            violence_enabled=settings.get("violence_enabled", True),
            violence_threshold=settings.get("violence_threshold", 0.75),
            violence_weight=settings.get("violence_weight", 1.0),
            weapon_enabled=settings.get("weapon_enabled", False),
            weapon_threshold=settings.get("weapon_threshold", 0.55),
            weapon_weight=settings.get("weapon_weight", 0.9),
            crowd_surge_enabled=settings.get("crowd_surge_enabled", False),
            crowd_surge_threshold=settings.get("crowd_surge_threshold", 0.70),
            crowd_surge_weight=settings.get("crowd_surge_weight", 0.8),
            fall_enabled=settings.get("fall_enabled", False),
            fall_threshold=settings.get("fall_threshold", 0.65),
            fall_weight=settings.get("fall_weight", 0.85),
            intrusion_enabled=settings.get("intrusion_enabled", False),
            intrusion_threshold=settings.get("intrusion_threshold", 0.60),
            intrusion_weight=settings.get("intrusion_weight", 0.75),
            loitering_enabled=settings.get("loitering_enabled", False),
            loitering_threshold=settings.get("loitering_threshold", 0.50),
            loitering_weight=settings.get("loitering_weight", 0.6),
        )


class CategoryStatus(str, Enum):
    ACTIVE = "active"
    EXPERIMENTAL = "experimental"
    UNSUPPORTED = "unsupported"


class CategoryDetector:
    """Multi-category detection engine."""
    
    def __init__(self, config: CategoryConfig):
        self.config = config
        self._enabled_categories: List[DetectionCategory] = [
            cat for cat in DetectionCategory
            if getattr(config, f"{cat.value}_enabled", False)
        ]
    
    @property
    def enabled_categories(self) -> List[DetectionCategory]:
        return self._enabled_categories
    
    def is_category_enabled(self, category: DetectionCategory) -> bool:
        return category in self._enabled_categories
        
    def get_capability(self, category: DetectionCategory, weapon_ready: bool = False) -> Dict[str, Any]:
        """Get honest capability metadata for a category."""
        base = {
            "id": category.value,
            "label": category.name.replace("_", " ").title(),
            "enabled": self.is_category_enabled(category),
            "threshold": getattr(self.config, f"{category.value}_threshold", 0.0),
            "status": CategoryStatus.UNSUPPORTED.value,
            "reason": "Not implemented",
            "requiredInputs": []
        }
        
        if category == DetectionCategory.VIOLENCE:
            base["status"] = CategoryStatus.ACTIVE.value
            base["reason"] = "X3D violence inference is configured and active."
            base["requiredInputs"] = ["video_window"]
            
        elif category == DetectionCategory.WEAPON:
            if weapon_ready:
                base["status"] = CategoryStatus.EXPERIMENTAL.value
                base["reason"] = "YOLO weapon model connected but pending precision validation."
                base["requiredInputs"] = ["frame_image"]
            else:
                base["status"] = CategoryStatus.UNSUPPORTED.value
                base["reason"] = "Weapon engine not loaded or unavailable."
                base["requiredInputs"] = ["yolo_weights"]
                base["enabled"] = False # Force disabled if unsupported
                
        elif category == DetectionCategory.CROWD_SURGE:
            base["status"] = CategoryStatus.EXPERIMENTAL.value
            base["reason"] = "Basic optical flow density heuristic. Lacks stateful tracking."
            base["requiredInputs"] = ["optical_flow"]
            
        elif category == DetectionCategory.FALL:
            base["status"] = CategoryStatus.UNSUPPORTED.value
            base["reason"] = "Temporal pose estimation not yet integrated."
            base["requiredInputs"] = ["pose_estimation", "person_boxes"]
            base["enabled"] = False
            
        elif category == DetectionCategory.INTRUSION:
            base["status"] = CategoryStatus.UNSUPPORTED.value
            base["reason"] = "Restricted zones configuration missing."
            base["requiredInputs"] = ["zone_polygons", "person_boxes"]
            base["enabled"] = False
            
        elif category == DetectionCategory.LOITERING:
            base["status"] = CategoryStatus.UNSUPPORTED.value
            base["reason"] = "Dwell-time logic and person re-ID not implemented."
            base["requiredInputs"] = ["tracking_ids", "dwell_timers"]
            base["enabled"] = False

        return base
    
    def analyze_frame(
        self, 
        frame: np.ndarray, 
        category: DetectionCategory,
        base_confidence: float = 0.0,
    ) -> Dict[DetectionCategory, float]:
        """
        Analyze a frame for a specific category.
        Returns scores for the requested category.
        """
        scores: Dict[DetectionCategory, float] = {}
        
        # Don't analyze if disabled OR unsupported
        if not self.is_category_enabled(category):
            return scores
            
        cap = self.get_capability(category)
        if cap["status"] == CategoryStatus.UNSUPPORTED.value:
            return scores
        
        if category == DetectionCategory.VIOLENCE:
            scores[category] = base_confidence  # Use X3D confidence
        
        elif category == DetectionCategory.WEAPON:
            # Delegated to weapon.py - placeholder here
            scores[category] = 0.0
        
        elif category == DetectionCategory.CROWD_SURGE:
            scores[category] = self._detect_crowd_surge(frame)
        
        elif category == DetectionCategory.FALL:
            scores[category] = self._detect_fall(frame)
        
        elif category == DetectionCategory.INTRUSION:
            scores[category] = self._detect_intrusion(frame)
        
        elif category == DetectionCategory.LOITERING:
            scores[category] = self._detect_loitering(frame)
        
        return scores
    
    def _detect_crowd_surge(self, frame: np.ndarray) -> float:
        """Detect crowd surge based on optical flow density."""
        gray = np.mean(frame, axis=2) if frame.ndim == 3 else frame
        movement_score = float(np.std(gray) / 255.0)
        threshold = self.config.crowd_surge_threshold
        return min(1.0, movement_score / threshold) if movement_score > threshold else 0.0
    
    def _detect_fall(self, frame: np.ndarray) -> float:
        """Detect human fall based on aspect ratio changes."""
        # Simplified: would use pose estimation in production
        return 0.0
    
    def _detect_intrusion(self, frame: np.ndarray) -> float:
        """Detect intrusion in restricted areas."""
        # Simplified: would use zone-based detection
        return 0.0
    
    def _detect_loitering(self, frame: np.ndarray) -> float:
        """Detect loitering behavior."""
        # Simplified: would track dwell time
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
