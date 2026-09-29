"""The retired identity-policy API stays absent; incident face capture is explicit.

Face matching/policy helpers are disconnected code in the campaign baseline.
Do not initialize unrelated model engines or waive calibration to test them.
The supported service detects incident faces and reports uncertain association.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import api
from security import AccessConfig, AccessController


class FacePolicyTests(unittest.TestCase):
    def test_retired_identity_policy_routes_are_not_published(self):
        client = TestClient(api.app)
        for method, path in (("GET", "/face/policy"), ("POST", "/face/policy"),
                             ("POST", "/face/policy/reload"), ("GET", "/face/status")):
            with self.subTest(method=method, path=path):
                self.assertEqual(client.request(method, path, json={}).status_code, 404)

    def test_incident_face_health_reports_disabled_service(self):
        with patch.object(api, "security_controller", AccessController(AccessConfig())), \
             patch.object(api, "_get_face_service", return_value=None), \
             patch.object(api, "_face_build_error", "detector unavailable"):
            response = TestClient(api.app).get("/api/faces/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "DISABLED")
        self.assertEqual(response.json()["reason"], "detector unavailable")

    def test_incident_face_reads_require_configured_credential(self):
        with patch.object(api, "security_controller", AccessController(AccessConfig("face-test-key"))), \
             patch.object(api, "_get_face_service", return_value=None):
            client = TestClient(api.app)
            for path in ("/api/faces/health", "/api/faces/incidents/incident-test"):
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 401)
            authorized = client.get("/api/faces/health", headers={"X-API-Key": "face-test-key"})
        self.assertEqual(authorized.status_code, 200)

    def test_missing_incident_capture_does_not_fabricate_identity(self):
        with patch.object(api, "security_controller", AccessController(AccessConfig())), \
             patch.object(api, "_get_face_service", return_value=None):
            response = TestClient(api.app).get("/api/faces/incidents/incident-test")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Face capture unavailable", response.json()["detail"])
        self.assertNotIn("recognized", response.json())


if __name__ == "__main__":
    unittest.main()
