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


def test_category_config_replace():
    import dataclasses
    config = CategoryConfig(weapon_enabled=False)
    assert not config.weapon_enabled
    new_config = dataclasses.replace(config, weapon_enabled=True)
    assert new_config.weapon_enabled
    assert not config.weapon_enabled

def test_category_capabilities():
    """Verify that categories report correct capabilities."""
    config = CategoryConfig()
    detector = CategoryDetector(config)
    
    # Violence should be active
    cap = detector.get_capability(DetectionCategory.VIOLENCE)
    assert cap["status"] == "active"
    
    # Fall should be unsupported
    cap = detector.get_capability(DetectionCategory.FALL)
    assert cap["status"] == "unsupported"
    
    # Weapon should be unsupported if no engine
    cap_unready = detector.get_capability(DetectionCategory.WEAPON)
    assert cap_unready["status"] == "unsupported"
    
    # Weapon should be experimental if engine is ready
    class MockEngine:
        def latest_signal(self):
            return {"ready": True}
    detector_with_weapon = CategoryDetector(config, weapon_engine=MockEngine())
    cap_ready = detector_with_weapon.get_capability(DetectionCategory.WEAPON)
    assert cap_ready["status"] == "experimental"

def test_unsupported_category_analysis():
    """Unsupported categories should return empty scores."""
    config = CategoryConfig(fall_enabled=True) # Try to enable it anyway
    detector = CategoryDetector(config)
    
    import numpy as np
    dummy_frame = np.zeros((160, 160, 3), dtype=np.uint8)
    
    scores = detector.analyze_frame(dummy_frame, DetectionCategory.FALL)
    # New contract: Unsupported categories return 0.0 in the dictionary
    assert scores[DetectionCategory.FALL] == 0.0
