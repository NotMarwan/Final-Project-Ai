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
    assert "connected" in cap["reason"]
    assert "slow" in cap["reason"]


def test_weapon_engine_concurrency_skipping():
    """Verify that concurrent calls increment skipped_frames."""
    from weapon import WeaponSignalEngine, WeaponConfig
    import numpy as np
    
    config = WeaponConfig(enabled=True, interval=1, min_interval_ms=0)
    engine = WeaponSignalEngine(config)
    # Mock model to simulate "running"
    engine._model = object() 
    engine._inference_running = True
    
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    engine.process_frame(frame)
    engine.process_frame(frame)
    
    signal = engine.latest_signal()
    assert signal["skippedFrames"] == 2
    assert signal["inferenceRunning"] is True

def test_weapon_engine_cooldown_skipping():
    """Verify that calls within min_interval_ms are skipped.

    Repaired (WT-18): the gate is the monotonic start interval
    (`_last_start_monotonic`), not the wall-clock status field
    `_last_inference_at`; the previous version set `engine._model`, an
    attribute removed with the torchvision path, and failed on baseline.
    """
    from weapon import WeaponSignalEngine, WeaponConfig
    import numpy as np
    import time
    
    config = WeaponConfig(enabled=True, interval=1, min_interval_ms=1000)
    engine = WeaponSignalEngine(config)
    engine._last_start_monotonic = time.monotonic()  # A run just started.
    engine._last_inference_at = time.time()
    
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    engine.process_frame(frame)
    
    signal = engine.latest_signal()
    assert signal["skippedFrames"] == 1
    assert signal["inferenceRunning"] is False

def test_weapon_realtime_flag():
    """Verify isRealtime flag logic."""
    from weapon import WeaponSignalEngine, WeaponConfig
    
    config = WeaponConfig(enabled=True, realtime_threshold_ms=500)
    engine = WeaponSignalEngine(config)
    engine._model = object()
    engine._backend = object()
    
    # Case 1: Slow
    engine._last_inference_latency_ms = 600
    assert engine.latest_signal()["isRealtime"] is False
    
    # Case 2: Fast
    engine._last_inference_latency_ms = 400
    assert engine.latest_signal()["isRealtime"] is True

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


# ──────────────────────────────────────────────────────────────────────────────
# WT-18 additions: config-driven taxonomy mapping (F-09 boundary). Alert
# severity must key on coarse groups; subtype mapping errors cannot flip it.
# ──────────────────────────────────────────────────────────────────────────────

import pytest as _pytest

from weapon_taxonomy import (GROUP_EDGED, GROUP_FALLBACK, GROUP_FIREARM,
                             TaxonomyConfigError, WeaponTaxonomy, default_taxonomy)


def test_taxonomy_from_sc5_mapping_table():
    taxonomy = WeaponTaxonomy.from_mapping({
        "firearm": ["pistol", "revolver", "rifle", "shotgun"],
        "edged": ["knife", "sword"],
        "fallback_group": "other-weapon",
    })
    assert taxonomy.group_for("pistol") == GROUP_FIREARM
    assert taxonomy.group_for("knife") == GROUP_EDGED
    assert taxonomy.group_for("machete") == GROUP_FALLBACK


def test_taxonomy_rejects_invalid_configuration():
    with _pytest.raises(TaxonomyConfigError, match="disjoint"):
        WeaponTaxonomy(firearm=("pistol", "knife"), edged=("knife",))
    with _pytest.raises(TaxonomyConfigError, match="nonempty"):
        WeaponTaxonomy(firearm=(), edged=("knife",))
    with _pytest.raises(TaxonomyConfigError, match="fallback_group"):
        WeaponTaxonomy(firearm=("pistol",), edged=("knife",), fallback_group="  ")
    with _pytest.raises(TaxonomyConfigError, match="unknown taxonomy keys"):
        WeaponTaxonomy.from_mapping({"firearm": ["pistol"], "edged": ["knife"],
                                     "sevretiy": 1})
    with _pytest.raises(TaxonomyConfigError, match="two alias pairs"):
        WeaponTaxonomy(firearm=("pistol",), edged=("knife",),
                       alias_pairs=(("pistol", "revolver"), ("revolver", "gun")))


def test_mapping_error_cannot_flip_severity_key():
    """The severity key is the coarse group: confusing any two subtypes of a
    group (the classic pistol/revolver and knife/sword CCTV failures) leaves
    severity identical, and cross-group confusion is caught by disjointness."""
    taxonomy = default_taxonomy()
    for left, right in (("pistol", "revolver"), ("rifle", "shotgun"),
                        ("knife", "sword")):
        assert taxonomy.severity_key(left) == taxonomy.severity_key(right)
    assert taxonomy.severity_key("pistol") != taxonomy.severity_key("knife")
    # Foreign labels never escalate: they fall to the fallback group.
    assert taxonomy.severity_key("toy-gun") == GROUP_FALLBACK
    # Canonical alert labels collapse unresolvable subtype pairs.
    assert taxonomy.canonical_label("revolver") == "pistol"
    assert taxonomy.canonical_label("sword") == "knife"
    assert taxonomy.canonical_label("rifle") == "rifle"

