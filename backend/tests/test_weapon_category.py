import pytest
import numpy as np
from detection_categories import CategoryDetector, DetectionCategory, CategoryConfig

class MockWeaponEngine:
    def __init__(self, ready=True, loading=False, failed=False, score=0.0, should_raise=False):
        self.ready = ready
        self.loading = loading
        self.failed = failed
        self.score = score
        self.should_raise = should_raise

    def latest_signal(self):
        return {
            "ready": self.ready, 
            "loading": self.loading, 
            "failed": self.failed, 
            "score": self.score
        }

    def process_frame(self, frame):
        if self.should_raise:
            raise RuntimeError("Mock engine crashed")
        return self.latest_signal()


def test_weapon_capability_unavailable_no_engine():
    """Weapon capability reports unavailable when no weapon engine is injected."""
    config = CategoryConfig(weapon_enabled=True)
    detector = CategoryDetector(config)
    cap = detector.get_capability(DetectionCategory.WEAPON)
    
    assert cap["status"] == "unsupported"
    assert cap["enabled"] is False

def test_weapon_capability_experimental_with_engine():
    """Weapon capability reports experimental when a mock ready engine is injected."""
    config = CategoryConfig(weapon_enabled=True)
    detector = CategoryDetector(config, weapon_engine=MockWeaponEngine(ready=True))
    cap = detector.get_capability(DetectionCategory.WEAPON)
    
    assert cap["status"] == "experimental"
    assert cap["enabled"] is True

def test_weapon_analysis_triggered_score():
    """Weapon analysis returns score when mock engine returns score."""
    config = CategoryConfig(weapon_enabled=True, weapon_threshold=0.55)
    detector = CategoryDetector(config, weapon_engine=MockWeaponEngine(ready=True, score=0.85))
    
    dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    scores = detector.analyze_frame(dummy_frame, DetectionCategory.WEAPON)
    
    assert DetectionCategory.WEAPON in scores
    assert scores[DetectionCategory.WEAPON] == 0.85

def test_weapon_analysis_non_triggered_score():
    """Weapon analysis returns score when mock engine score is below threshold."""
    # Note: Trigger logic is typically handled by the caller checking if score > threshold,
    # analyze_frame just returns the raw score. We verify the score is returned correctly.
    config = CategoryConfig(weapon_enabled=True, weapon_threshold=0.55)
    detector = CategoryDetector(config, weapon_engine=MockWeaponEngine(ready=True, score=0.20))
    
    dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    scores = detector.analyze_frame(dummy_frame, DetectionCategory.WEAPON)
    
    assert DetectionCategory.WEAPON in scores
    assert scores[DetectionCategory.WEAPON] == 0.20

def test_weapon_analysis_engine_exception():
    """Weapon analysis handles engine exceptions safely by returning 0.0."""
    config = CategoryConfig(weapon_enabled=True)
    detector = CategoryDetector(config, weapon_engine=MockWeaponEngine(ready=True, should_raise=True))
    
    dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    scores = detector.analyze_frame(dummy_frame, DetectionCategory.WEAPON)
    
    assert DetectionCategory.WEAPON in scores
    assert scores[DetectionCategory.WEAPON] == 0.0
