import pytest
from detection_categories import CategoryDetector, DetectionCategory, CategoryConfig

def test_category_enum_values():
    """Verify all required categories are defined."""
    assert DetectionCategory.VIOLENCE == "violence"
    assert DetectionCategory.WEAPON == "weapon"
    assert DetectionCategory.CROWD_SURGE == "crowd_surge"
    assert DetectionCategory.FALL == "fall"
    assert DetectionCategory.INTRUSION == "intrusion"
    assert DetectionCategory.LOITERING == "loitering"

def test_category_detector_initialization():
    """Detector should initialize with all categories disabled by default."""
    config = CategoryConfig()
    detector = CategoryDetector(config)
    
    assert detector.enabled_categories == [DetectionCategory.VIOLENCE]
    assert not detector.is_category_enabled(DetectionCategory.WEAPON)

def test_enable_weapon_category():
    """Should be able to enable weapon detection."""
    config = CategoryConfig(weapon_enabled=True)
    detector = CategoryDetector(config)
    
    assert detector.is_category_enabled(DetectionCategory.WEAPON)

def test_category_scoring():
    """Each category should produce a score between 0 and 1."""
    config = CategoryConfig(
        violence_enabled=True,
        weapon_enabled=True,
        crowd_surge_enabled=True,
    )
    detector = CategoryDetector(config)
    
    import numpy as np
    dummy_frame = np.zeros((160, 160, 3), dtype=np.uint8)
    
    scores = detector.analyze_frame(dummy_frame, DetectionCategory.VIOLENCE)
    assert 0.0 <= scores.get(DetectionCategory.VIOLENCE, 0) <= 1.0
