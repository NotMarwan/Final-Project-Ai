import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

@pytest.fixture
def client(monkeypatch):
    import api
    from api import app
    from fastapi.testclient import TestClient
    
    # Initialize basic globals with mocks to avoid NoneErrors
    mock_audit = MagicMock()
    mock_security = MagicMock()
    mock_security.authorize.return_value = "admin"
    
    monkeypatch.setattr(api, "audit_logger", mock_audit)
    monkeypatch.setattr(api, "security_controller", mock_security)
    monkeypatch.setattr(api, "config", {"server": {"cors_origins": ["*"]}, "model": {"confidence_threshold": 0.5, "stride": 16}, "storage": {"evidence_dir": "ev", "thumbnails_dir": "th"}})
    
    return TestClient(app)

@pytest.fixture
def api_module():
    import api
    return api

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

def test_api_refuses_to_enable_weapon_when_engine_unavailable(client, api_module, monkeypatch):
    """API refuses to enable weapon when the engine is unavailable."""
    from detection_categories import CategoryDetector, CategoryConfig
    # Mock the weapon engine to be unavailable
    monkeypatch.setattr(api_module, "weapon_engine", MockWeaponEngineUnavailable())
    
    # Re-initialize the category detector with the mocked engine
    api_module.category_detector = CategoryDetector(CategoryConfig(), weapon_engine=MockWeaponEngineUnavailable())
    
    # Attempt to enable weapon category
    response = client.post(
        "/api/categories/weapon/toggle?enabled=true",
        headers={"Authorization": "Bearer fake_admin_token"}
    )
    
    assert response.status_code == 400
    assert "Cannot enable weapon" in response.json()["detail"]

def test_api_allows_weapon_toggle_when_engine_available(client, api_module, monkeypatch):
    """API allows weapon toggle only when capability says it is available."""
    from detection_categories import CategoryDetector, CategoryConfig
    # Mock the weapon engine to be ready
    monkeypatch.setattr(api_module, "weapon_engine", MockWeaponEngineReady())
    
    # Re-initialize the category detector with the mocked engine
    api_module.category_detector = CategoryDetector(CategoryConfig(), weapon_engine=MockWeaponEngineReady())
    
    # Mock the authorize method to always pass
    class MockSecurityController:
        def authorize(self, request, required_role):
            return "admin"
    monkeypatch.setattr(api_module, "security_controller", MockSecurityController())
    
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
