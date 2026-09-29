import numpy as np


def test_read_weapon_signal_uses_cached_bbox_and_score_for_visual_continuity():
    from backend.inference_process import read_weapon_signal

    class StubWeaponEngine:
        def process_frame(self, frame):
            return {
                "score": 0.4182,
                "labels": ["knife"],
                "bbox": [0.25, 0.35, 0.58, 0.82],
            }

        def latest_signal(self):
            return {
                "score": 0.4182,
                "labels": ["knife"],
                "bbox": [0.25, 0.35, 0.58, 0.82],
            }

    score, labels, bbox = read_weapon_signal(
        StubWeaponEngine(),
        np.zeros((16, 16, 3), dtype=np.uint8),
    )

    assert score == 0.4182
    assert labels == ["knife"]
    assert bbox == [0.25, 0.35, 0.58, 0.82]


def test_detection_payload_keeps_multi_threat_boxes_for_frontend_overlay():
    from backend.api import _build_detection_payload

    multi_threat = {
        "hasViolence": False,
        "hasWeapon": True,
        "isMultiThreat": False,
        "violenceScore": 0.0,
        "weaponScore": 41.8,
        "fusedScore": 41.8,
        "severity": "medium",
        "threatBoxes": [
            {
                "id": "weapon-knife",
                "type": "weapon",
                "weaponType": "knife",
                "bbox": [0.25, 0.35, 0.58, 0.82],
                "confidence": 0.418,
                "color": [245, 158, 11],
                "label": "KNIFE",
            }
        ],
        "reason": "weapon-watch",
    }
    snap = {
        "tracks": [],
        "person_count": 0,
        "is_threat": True,
        "threat_confidence": 41.8,
        "fps": 8.4,
        "weapon_score": 0.418,
        "video_width": 640,
        "video_height": 480,
        "multiThreat": multi_threat,
        "inference_sequence": 1,
        "weapon_observation_id": 1,
        "violence_observation_id": 0,
    }

    payload = _build_detection_payload(snap)

    assert payload["isThreat"] is True
    assert payload["weaponScore"] == 0.418
    assert payload["multiThreat"] == multi_threat


def test_multi_threat_prefers_top_ranked_knife_label_over_lower_ranked_gun_labels():
    from backend.fusion import FusionConfig, ThreatFusionEngine

    engine = ThreatFusionEngine(FusionConfig())
    result = engine.assess_multi_threat(
        violence_confidence=0.0,
        weapon_score=engine.config.policy.weapon_display_threshold,
        weapon_bbox=[120, 90, 210, 260],
        weapon_labels=["knife", "pistol", "rifle"],
    )

    threat_box = result["multiThreat"]["threatBoxes"][0]
    assert threat_box["weaponType"] == "knife"
    assert threat_box["label"] == "KNIFE"
