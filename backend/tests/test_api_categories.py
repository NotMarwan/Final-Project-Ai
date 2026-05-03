import pytest
from fastapi.testclient import TestClient
from api import app, weapon_engine
from detection_categories import CategoryDetector, CategoryConfig
import api

client = TestClient(app)

class MockWeaponEngineReady:
    def status(self):
        return {"ready": True, "loading": False, "failed": False}
    def latest_signal(self):
        return {"ready": True, "loading": False, "failed": False, "score": 0.0}

class MockWeaponEngineUnavailable:
    def status(self):
        return {"ready": False, "loading": False, "failed": True}
    def latest_signal(self):
        return {"ready": False, "loading": False, "failed": True, "reason": "Not loaded"}

def test_api_refuses_to_enable_weapon_when_engine_unavailable(monkeypatch):
    """API refuses to enable weapon when the engine is unavailable."""
    # Mock the weapon engine to be unavailable
    monkeypatch.setattr(api, "weapon_engine", MockWeaponEngineUnavailable())
    
    # Re-initialize the category detector with the mocked engine
    api.category_detector = CategoryDetector(CategoryConfig(), weapon_engine=MockWeaponEngineUnavailable())
    
    # Attempt to enable weapon category
    response = client.post(
        "/api/categories/weapon/toggle?enabled=true",
        headers={"Authorization": "Bearer fake_admin_token"}
    )
    
    assert response.status_code == 400
    assert "Cannot enable weapon" in response.json()["detail"]

def test_api_allows_weapon_toggle_when_engine_available(monkeypatch):
    """API allows weapon toggle only when capability says it is available."""
    # Mock the weapon engine to be ready
    monkeypatch.setattr(api, "weapon_engine", MockWeaponEngineReady())
    
    # Re-initialize the category detector with the mocked engine
    api.category_detector = CategoryDetector(CategoryConfig(), weapon_engine=MockWeaponEngineReady())
    
    # Mock the authorize method to always pass
    class MockSecurityController:
        def authorize(self, request, required_role):
            return "admin"
    monkeypatch.setattr(api, "security_controller", MockSecurityController())
    
    # Attempt to enable weapon category
    response = client.post(
        "/api/categories/weapon/toggle?enabled=true"
    )
    
    assert response.status_code == 200
    assert response.json()["enabled"] is True
    
    # Attempt to disable weapon category
    response_disable = client.post(
        "/api/categories/weapon/toggle?enabled=false"
    )
    
    assert response_disable.status_code == 200
    assert response_disable.json()["enabled"] is False
