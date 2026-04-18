import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from face_intel import FaceIntelEngine


class FacePolicyPersistenceTests(unittest.TestCase):
    def test_policy_overrides_are_saved_and_reloaded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            settings = {
                "face_intel": {
                    "enabled": False,
                    "detector_backend": "none",
                    "policy_overrides_path": "./face_policy_overrides.json",
                }
            }

            first_engine = FaceIntelEngine.from_settings(settings, {}, base_dir)
            self.assertTrue(first_engine.config.identity_labeling_enabled)
            self.assertTrue(first_engine.config.recognition_audit_enabled)
            self.assertEqual(first_engine.config.recognition_audit_cooldown_sec, 25)

            first_engine.set_identity_labeling_enabled(False)
            first_engine.set_recognition_audit_enabled(False)
            first_engine.set_recognition_audit_cooldown_sec(44)

            overrides_path = base_dir / "face_policy_overrides.json"
            self.assertTrue(overrides_path.exists())

            payload = json.loads(overrides_path.read_text(encoding="utf-8"))
            self.assertEqual(payload.get("identityLabelingEnabled"), False)
            self.assertEqual(payload.get("recognitionAuditEnabled"), False)
            self.assertEqual(payload.get("recognitionAuditCooldownSec"), 44)

            reloaded_engine = FaceIntelEngine.from_settings(settings, {}, base_dir)
            self.assertFalse(reloaded_engine.config.identity_labeling_enabled)
            self.assertFalse(reloaded_engine.config.recognition_audit_enabled)
            self.assertEqual(reloaded_engine.config.recognition_audit_cooldown_sec, 44)


if __name__ == "__main__":
    unittest.main()
