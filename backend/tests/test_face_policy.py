import importlib.util
import os
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


def _load_api_module():
    project_root = Path(__file__).resolve().parents[2]
    backend_dir = project_root / "backend"
    module_path = backend_dir / "api.py"

    os.environ["AI_SENTINEL_ENABLE_CAPTURE_LOOP"] = "false"
    os.environ["ADMIN_API_KEY"] = ""

    backend_dir_text = str(backend_dir)
    if backend_dir_text not in sys.path:
        sys.path.insert(0, backend_dir_text)

    module_name = "ai_sentinel_api_test_module"
    if module_name in sys.modules:
        del sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load backend/api.py for tests.")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class FacePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = _load_api_module()

    def test_public_face_summary_masks_known_identity_when_policy_off(self):
        raw_summary = {
            "enabled": True,
            "identityLabelingEnabled": False,
            "frameIndex": 42,
            "totalFaces": 2,
            "recognized": [
                {"personId": "person-001", "label": "Alice", "confidence": 0.91},
            ],
            "recognizedCount": 1,
            "unknownIds": ["U-001"],
            "unknownCount": 1,
            "unknownDetails": [{"id": "U-001"}],
            "observations": [
                {"id": "person-001", "label": "Alice", "kind": "known", "confidence": 0.91, "bbox": [1, 2, 3, 4]},
                {"id": "U-001", "label": "U-001", "kind": "unknown", "confidence": 0.0, "bbox": [5, 6, 7, 8]},
            ],
        }

        public_summary = self.api._public_face_summary(raw_summary)

        self.assertFalse(public_summary["identityLabelingEnabled"])
        self.assertEqual(public_summary["recognizedCount"], 1)
        self.assertEqual(public_summary["unknownIds"], ["U-001"])

        recognized_person = public_summary["recognized"][0]
        self.assertTrue(recognized_person["personId"].startswith("K-"))
        self.assertEqual(recognized_person["label"], recognized_person["personId"])
        self.assertTrue(recognized_person["masked"])

        known_observation = next(obs for obs in public_summary["observations"] if obs["kind"] == "known")
        self.assertEqual(known_observation["id"], recognized_person["personId"])
        self.assertEqual(known_observation["label"], recognized_person["label"])

        unknown_observation = next(obs for obs in public_summary["observations"] if obs["kind"] == "unknown")
        self.assertEqual(unknown_observation["id"], "U-001")
        self.assertEqual(unknown_observation["label"], "U-001")

    def test_face_policy_endpoint_updates_runtime_policy(self):
        with TestClient(self.api.app) as client:
            update_payload = {
                "identity_labeling_enabled": False,
                "recognition_audit_enabled": False,
                "recognition_audit_cooldown_sec": 33,
            }
            update_response = client.post("/face/policy", json=update_payload)
            self.assertEqual(update_response.status_code, 200, update_response.text)

            body = update_response.json()
            self.assertEqual(body["status"], "success")
            self.assertEqual(body["updates"]["identityLabelingEnabled"], False)
            self.assertEqual(body["updates"]["recognitionAuditEnabled"], False)
            self.assertEqual(body["updates"]["recognitionAuditCooldownSec"], 33)

            status_response = client.get("/face/status")
            self.assertEqual(status_response.status_code, 200, status_response.text)
            status_body = status_response.json()
            policy = status_body.get("policy", {})
            self.assertEqual(policy.get("identityLabelingEnabled"), False)
            self.assertEqual(policy.get("recognitionAuditEnabled"), False)
            self.assertEqual(policy.get("recognitionAuditCooldownSec"), 33)

            client.post(
                "/face/policy",
                json={
                    "identity_labeling_enabled": True,
                    "recognition_audit_enabled": True,
                    "recognition_audit_cooldown_sec": 25,
                },
            )


if __name__ == "__main__":
    unittest.main()
