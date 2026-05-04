import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add backend to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    from api import app
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c

def test_api_categories_returns_camelcase_contract(client):
    """/api/categories returns requiresContext and requiredInputs in camelCase."""
    resp = client.get("/api/categories")
    assert resp.status_code == 200
    cats = resp.json()["categories"]
    intrusion = next(c for c in cats if c["id"] == "intrusion")
    assert "requiresContext" in intrusion
    assert "requiredInputs" in intrusion
    assert intrusion["requiresContext"] is True
    assert "personBoxes" in intrusion["requiredInputs"]
    assert "restrictedZones" in intrusion["requiredInputs"]

def test_api_analyze_accepts_camelcase(client):
    """/api/analyze accepts camelCase context."""
    payload = {
        "category": "intrusion",
        "context": {
            "cameraId": "CAM-01",
            "personBoxes": [{"x1": 10, "y1": 10, "x2": 50, "y2": 50}],
            "restrictedZones": [{"id": "z1", "name": "Z", "bbox": [0, 0, 100, 100]}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert data["category"] == "intrusion"

def test_api_analyze_accepts_snakecase(client):
    """/api/analyze accepts snake_case context."""
    payload = {
        "category": "intrusion",
        "context": {
            "camera_id": "CAM-01",
            "person_boxes": [{"x1": 10, "y1": 10, "x2": 50, "y2": 50}],
            "restricted_zones": [{"id": "z1", "name": "Z", "bbox": [0, 0, 100, 100]}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 200

def test_malformed_person_boxes_returns_400(client):
    payload = {"category": "intrusion", "context": {"personBoxes": "not-a-list"}}
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "personBoxes must be a list" in resp.json()["detail"]

def test_malformed_restricted_zones_returns_400(client):
    payload = {"category": "intrusion", "context": {"restrictedZones": "not-a-list"}}
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "restrictedZones must be a list" in resp.json()["detail"]

def test_invalid_bbox_length_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {
            "restrictedZones": [{"id": "z1", "bbox": [0, 0, 100]}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "bbox must be a list/tuple of 4" in resp.json()["detail"]

def test_non_numeric_bbox_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {
            "restrictedZones": [{"id": "z1", "bbox": [0, 0, 100, "fail"]}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "bbox values must be numeric" in resp.json()["detail"]

def test_bbox_x2_lt_x1_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {
            "restrictedZones": [{"id": "z1", "bbox": [100, 0, 50, 100]}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "bbox coordinates invalid" in resp.json()["detail"]

def test_bbox_y2_lt_y1_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {
            "restrictedZones": [{"id": "z1", "bbox": [0, 100, 100, 50]}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "bbox coordinates invalid" in resp.json()["detail"]

def test_non_numeric_box_coords_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {
            "personBoxes": [{"x1": "fail", "y1": 10, "x2": 50, "y2": 50}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "coordinates must be numeric" in resp.json()["detail"]

def test_box_x2_lt_x1_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {
            "personBoxes": [{"x1": 100, "y1": 10, "x2": 50, "y2": 50}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "Box x2 must be >= x1" in resp.json()["detail"]

def test_box_y2_lt_y1_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {
            "personBoxes": [{"x1": 10, "y1": 100, "x2": 50, "y2": 50}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "Box y2 must be >= y1" in resp.json()["detail"]

def test_intrusion_threshold_out_of_range_low_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {"intrusionThreshold": -0.1}
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "must be between 0.0 and 1.0" in resp.json()["detail"]

def test_intrusion_threshold_out_of_range_high_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {"intrusionThreshold": 1.5}
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "must be between 0.0 and 1.0" in resp.json()["detail"]

def test_intrusion_threshold_zero_accepted(client):
    payload = {
        "category": "intrusion",
        "context": {
            "cameraId": "CAM-01",
            "personBoxes": [{"x1": 10, "y1": 10, "x2": 50, "y2": 50}],
            "restrictedZones": [{"id": "z1", "bbox": [0, 0, 100, 100], "intrusionThreshold": 0}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 200

def test_snake_case_threshold_accepted(client):
    payload = {
        "category": "intrusion",
        "context": {"intrusion_threshold": 0}
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 200

def test_missing_zone_id_returns_400(client):
    payload = {
        "category": "intrusion",
        "context": {
            "restrictedZones": [{"bbox": [0, 0, 100, 100]}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 400
    assert "Zone requires an id" in resp.json()["detail"]

def test_missing_zone_name_allowed(client):
    """Zone name is optional in the backend, should be allowed."""
    payload = {
        "category": "intrusion",
        "context": {
            "restrictedZones": [{"id": "z1", "bbox": [0, 0, 100, 100]}]
        }
    }
    resp = client.post("/api/analyze", json=payload)
    assert resp.status_code == 200
