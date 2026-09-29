import pytest
import numpy as np
from backend.detection_categories import (
    DetectionCategory, 
    DetectionContext, 
    Box, 
    Zone, 
    CategoryDetector, 
    CategoryConfig,
    CategoryStatus
)

@pytest.fixture
def detector():
    config = CategoryConfig(intrusion_enabled=True)
    return CategoryDetector(config)

def test_intrusion_capability_missing_inputs(detector):
    """Honest reporting: intrusion should be unsupported if context is missing inputs."""
    # No context
    cap = detector.get_capability(DetectionCategory.INTRUSION)
    assert cap["status"] == CategoryStatus.UNSUPPORTED.value
    assert "Requires restricted zones" in cap["reason"]
    
    # Context with zones but no persons
    ctx = DetectionContext(restricted_zones=[Zone("z1", "cam1", 0, 0, 100, 100)])
    cap = detector.get_capability(DetectionCategory.INTRUSION, ctx)
    assert cap["status"] == CategoryStatus.UNSUPPORTED.value
    assert "Requires person boxes" in cap["reason"]

def test_intrusion_capability_ready(detector):
    """Honest reporting: intrusion should be experimental if context has required inputs."""
    ctx = DetectionContext(
        person_boxes=[Box(10, 10, 20, 20)],
        restricted_zones=[Zone("z1", "cam1", 0, 0, 100, 100)]
    )
    cap = detector.get_capability(DetectionCategory.INTRUSION, ctx)
    assert cap["status"] == CategoryStatus.EXPERIMENTAL.value
    assert "active" in cap["reason"].lower()

def test_intrusion_logic_overlap(detector):
    """Verify minimal overlap detection logic."""
    # Case 1: Total overlap (Person entirely inside zone)
    ctx = DetectionContext(
        person_boxes=[Box(10, 10, 20, 20)], # Area 100
        restricted_zones=[Zone("z1", "cam1", 0, 0, 100, 100)]
    )
    scores = detector.analyze_context(ctx, DetectionCategory.INTRUSION)
    assert scores[DetectionCategory.INTRUSION] == 1.0

    # Case 2: Partial overlap (50%)
    # Person box: (0, 0) to (20, 10) -> Area 200
    # Zone: (10, 0) to (30, 10)
    # Intersection: (10, 0) to (20, 10) -> Area 100
    ctx = DetectionContext(
        person_boxes=[Box(0, 0, 20, 10)],
        restricted_zones=[Zone("z1", "cam1", 10, 0, 30, 10)]
    )
    scores = detector.analyze_context(ctx, DetectionCategory.INTRUSION)
    assert scores[DetectionCategory.INTRUSION] == 0.5

    # Case 3: No overlap
    ctx = DetectionContext(
        person_boxes=[Box(0, 0, 5, 5)],
        restricted_zones=[Zone("z1", "cam1", 10, 10, 20, 20)]
    )
    scores = detector.analyze_context(ctx, DetectionCategory.INTRUSION)
    assert scores[DetectionCategory.INTRUSION] == 0.0

def test_intrusion_camera_id_filtering(detector):
    """Verify that zones filter by camera_id if provided."""
    person = Box(10, 10, 20, 20)
    zone_cam1 = Zone("z1", "cam1", 0, 0, 100, 100)
    
    # Cam1 context -> match
    ctx1 = DetectionContext(camera_id="cam1", person_boxes=[person], restricted_zones=[zone_cam1])
    assert detector.analyze_context(ctx1, DetectionCategory.INTRUSION)[DetectionCategory.INTRUSION] == 1.0
    
    # Cam2 context -> no match
    ctx2 = DetectionContext(camera_id="cam2", person_boxes=[person], restricted_zones=[zone_cam1])
    assert detector.analyze_context(ctx2, DetectionCategory.INTRUSION)[DetectionCategory.INTRUSION] == 0.0

def test_intrusion_disabled_config():
    """Verify that intrusion returns 0 if disabled in config even if inputs are present."""
    config = CategoryConfig(intrusion_enabled=False)
    detector = CategoryDetector(config)
    ctx = DetectionContext(
        person_boxes=[Box(10, 10, 20, 20)],
        restricted_zones=[Zone("z1", "cam1", 0, 0, 100, 100)]
    )
    scores = detector.analyze_context(ctx, DetectionCategory.INTRUSION)
    assert scores[DetectionCategory.INTRUSION] == 0.0
