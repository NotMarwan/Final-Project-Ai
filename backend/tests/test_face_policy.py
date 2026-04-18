import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

_TEST_TEMP_DIR = tempfile.TemporaryDirectory()
_TEST_TMP_PATH = Path(_TEST_TEMP_DIR.name)


def _install_lightweight_stubs():
    if "torch" not in sys.modules:
        torch_stub = types.ModuleType("torch")

        class _Cuda:
            @staticmethod
            def is_available():
                return False

            @staticmethod
            def empty_cache():
                return None

        class _Device:
            def __init__(self, device_type: str):
                self.type = device_type

        def _device(device_type: str):
            return _Device(device_type)

        torch_stub.cuda = _Cuda()
        torch_stub.device = _device
        sys.modules["torch"] = torch_stub

    if "inference" not in sys.modules:
        inference_stub = types.ModuleType("inference")
        inference_stub.VIOLENCE_CLS = "Violence"

        class ViolenceInferencePipeline:
            def __init__(self, _weights_path, _device, threshold, _stride):
                self.threshold = threshold
                self._last_label = "Normal"
                self._last_conf = 0.0

            def process_frame(self, frame):
                return frame

            def reset(self):
                self._last_label = "Normal"
                self._last_conf = 0.0

        inference_stub.ViolenceInferencePipeline = ViolenceInferencePipeline
        sys.modules["inference"] = inference_stub


def _load_api_module():
    project_root = Path(__file__).resolve().parents[2]
    backend_dir = project_root / "backend"
    module_path = backend_dir / "api.py"

    os.environ["AI_SENTINEL_ENABLE_CAPTURE_LOOP"] = "false"
    os.environ["ADMIN_API_KEY"] = ""
    os.environ["FACE_POLICY_OVERRIDES_PATH"] = str((_TEST_TMP_PATH / "face_policy_overrides.json").resolve())
    os.environ["FACE_KNOWN_REGISTRY_PATH"] = str((_TEST_TMP_PATH / "known_faces_registry.json").resolve())
    _install_lightweight_stubs()

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

    def test_face_policy_endpoint_rejects_empty_payload(self):
        with TestClient(self.api.app) as client:
            response = client.post("/face/policy", json={})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertIn("No policy field provided", response.text)

    def test_face_policy_get_endpoint_returns_current_policy(self):
        with TestClient(self.api.app) as client:
            client.post(
                "/face/policy",
                json={
                    "identity_labeling_enabled": False,
                    "recognition_audit_enabled": True,
                    "recognition_audit_cooldown_sec": 21,
                },
            )

            response = client.get("/face/policy")
            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body.get("status"), "success")
            self.assertIsInstance(body.get("policyFetchedAt"), str)

            policy = body.get("policy", {})
            self.assertEqual(policy.get("identityLabelingEnabled"), False)
            self.assertEqual(policy.get("recognitionAuditEnabled"), True)
            self.assertEqual(policy.get("recognitionAuditCooldownSec"), 21)
            self.assertIsInstance(policy.get("policyUpdatedAt"), str)
            self.assertTrue(len(policy.get("policyUpdatedAt", "")) > 0)

    def test_face_policy_reload_endpoint_applies_disk_overrides(self):
        with TestClient(self.api.app) as client:
            client.post(
                "/face/policy",
                json={
                    "identity_labeling_enabled": False,
                    "recognition_audit_enabled": False,
                    "recognition_audit_cooldown_sec": 19,
                },
            )
            policy_response = client.get("/face/policy")
            self.assertEqual(policy_response.status_code, 200, policy_response.text)
            policy = policy_response.json().get("policy", {})
            overrides_path = Path(str(policy.get("policyOverridesPath", "")).strip())
            self.assertTrue(overrides_path.exists())

            disk_payload = {
                "identityLabelingEnabled": True,
                "recognitionAuditEnabled": True,
                "recognitionAuditCooldownSec": 27,
                "updatedAt": "2026-04-18T00:00:00+00:00",
            }
            overrides_path.write_text(json.dumps(disk_payload), encoding="utf-8")

            reload_response = client.post("/face/policy/reload")
            self.assertEqual(reload_response.status_code, 200, reload_response.text)
            body = reload_response.json()
            self.assertEqual(body.get("status"), "success")

            reloaded_policy = body.get("policy", {})
            self.assertEqual(reloaded_policy.get("identityLabelingEnabled"), True)
            self.assertEqual(reloaded_policy.get("recognitionAuditEnabled"), True)
            self.assertEqual(reloaded_policy.get("recognitionAuditCooldownSec"), 27)
            self.assertEqual(reloaded_policy.get("policyUpdatedAt"), "2026-04-18T00:00:00+00:00")

    def test_public_face_summary_alias_is_consistent_per_person(self):
        raw_summary = {
            "enabled": True,
            "identityLabelingEnabled": False,
            "recognized": [
                {"personId": "person-001", "label": "Alice", "confidence": 0.9},
                {"personId": "person-002", "label": "Bob", "confidence": 0.88},
            ],
            "recognizedCount": 2,
            "unknownIds": [],
            "unknownCount": 0,
            "unknownDetails": [],
            "observations": [
                {"id": "person-001", "label": "Alice", "kind": "known", "confidence": 0.9, "bbox": [1, 2, 3, 4]},
                {"id": "person-001", "label": "Alice", "kind": "known", "confidence": 0.87, "bbox": [2, 3, 4, 5]},
                {"id": "person-002", "label": "Bob", "kind": "known", "confidence": 0.88, "bbox": [6, 7, 8, 9]},
            ],
        }

        public_summary = self.api._public_face_summary(raw_summary)
        aliases = {item["personId"]: item["label"] for item in public_summary["recognized"]}
        self.assertEqual(len(aliases), 2)
        self.assertEqual(set(aliases.keys()), set(aliases.values()))

        known_obs = [obs for obs in public_summary["observations"] if obs["kind"] == "known"]
        self.assertEqual(known_obs[0]["id"], known_obs[1]["id"])
        self.assertNotEqual(known_obs[1]["id"], known_obs[2]["id"])
        self.assertTrue(all(obs["label"] == obs["id"] for obs in known_obs))

    def test_emit_face_audit_events_respects_cooldown_window(self):
        summary = {
            "identityLabelingEnabled": True,
            "frameIndex": 99,
            "recognized": [{"personId": "person-001", "label": "Alice", "confidence": 0.9}],
            "unknownIds": ["U-001"],
        }
        dedupe_cache = {}

        original_enabled = self.api.face_engine.config.recognition_audit_enabled
        original_cooldown = self.api.face_engine.config.recognition_audit_cooldown_sec
        self.api.face_engine.config.recognition_audit_enabled = True
        self.api.face_engine.config.recognition_audit_cooldown_sec = 10

        try:
            with patch.object(self.api.audit_logger, "record") as record_mock:
                with patch.object(self.api.time, "time", return_value=100.0):
                    self.api._emit_face_audit_events(
                        face_summary=summary,
                        camera_id="CAM-01",
                        dedupe_cache=dedupe_cache,
                    )
                self.assertEqual(record_mock.call_count, 2)

                record_mock.reset_mock()
                with patch.object(self.api.time, "time", return_value=105.0):
                    self.api._emit_face_audit_events(
                        face_summary=summary,
                        camera_id="CAM-01",
                        dedupe_cache=dedupe_cache,
                    )
                self.assertEqual(record_mock.call_count, 0)

                with patch.object(self.api.time, "time", return_value=110.0):
                    self.api._emit_face_audit_events(
                        face_summary=summary,
                        camera_id="CAM-01",
                        dedupe_cache=dedupe_cache,
                    )
                self.assertEqual(record_mock.call_count, 2)
        finally:
            self.api.face_engine.config.recognition_audit_enabled = original_enabled
            self.api.face_engine.config.recognition_audit_cooldown_sec = original_cooldown


if __name__ == "__main__":
    unittest.main()
