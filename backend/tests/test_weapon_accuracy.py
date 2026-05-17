"""
test_weapon_accuracy.py
=======================
Pytest tests for weapon detection model accuracy.

Validates that the weapon model meets the 90%+ accuracy threshold
and produces consistent, reliable detection results.
"""

import os
import sys
import json
import time
import pytest
import numpy as np

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _get_model_path() -> str:
    """Return path to the weapon model weights."""
    # best.pt is at the project root, one level up from backend/
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(backend_dir, "..", "best.pt")


def _create_test_frames(num_weapon: int = 50, num_non_weapon: int = 50) -> list[dict]:
    """Create synthetic test frames with known labels."""
    rng = np.random.RandomState(42)
    frames = []
    
    for _ in range(num_weapon):
        frame = rng.randint(30, 80, (480, 640, 3), dtype=np.uint8)
        x1, y1 = rng.randint(100, 400), rng.randint(50, 300)
        w, h = rng.randint(20, 80), rng.randint(60, 200)
        frame[y1:y1+h, x1:x1+w] = [rng.randint(40, 100), rng.randint(30, 70), rng.randint(30, 60)]
        frame[y1:y1+5, x1:x1+w] = [rng.randint(150, 220), rng.randint(150, 200), rng.randint(100, 150)]
        frames.append({"frame": frame, "label": 1})
    
    for _ in range(num_non_weapon):
        frame = rng.randint(100, 200, (480, 640, 3), dtype=np.uint8)
        cx, cy = rng.randint(100, 500), rng.randint(100, 350)
        import cv2
        cv2.circle(frame, (cx, cy), rng.randint(30, 80), (rng.randint(80, 180), rng.randint(80, 180), rng.randint(80, 180)), -1)
        frames.append({"frame": frame, "label": 0})
    
    return frames


@pytest.fixture(scope="module")
def weapon_engine():
    """Create a weapon engine instance for all tests in this module."""
    import torch
    from weapon import WeaponConfig, WeaponSignalEngine
    
    model_path = _get_model_path()
    if not os.path.exists(model_path):
        pytest.skip(f"Weapon model not found at {model_path}")
    
    config = WeaponConfig(
        enabled=True,
        backend="yolo",
        weight_path=model_path,
        labels=("pistol", "rifle", "shotgun", "knife", "sword", "revolver"),
        interval=1,
        min_interval_ms=0,
        min_confidence=0.20,
    )
    engine = WeaponSignalEngine(config, device=torch.device("cpu"))
    
    if not engine.preload():
        pytest.skip(f"Failed to load weapon model: {engine.status()['reason']}")
    
    return engine


class TestWeaponModelLoading:
    """Tests for weapon model loading and initialization."""

    def test_model_loads_successfully(self, weapon_engine):
        """Weapon model should load without errors."""
        signal = weapon_engine.latest_signal()
        assert signal["ready"] is True
        assert signal["failed"] is False
        assert signal["reason"] == "ok"

    def test_model_loads_on_cpu(self, weapon_engine):
        """Weapon model should work on CPU device."""
        assert str(weapon_engine.device) == "cpu"

    def test_model_load_latency_under_30s(self, weapon_engine):
        """Model load time should be under 30 seconds."""
        signal = weapon_engine.latest_signal()
        load_ms = signal.get("loadLatencyMs", 0)
        assert load_ms < 30000, f"Model load took {load_ms:.0f}ms, should be under 30000ms"

    def test_model_reports_correct_backend(self, weapon_engine):
        """Engine should report yolo backend."""
        signal = weapon_engine.latest_signal()
        assert signal["backend"] == "yolo"


class TestWeaponDetectionAccuracy:
    """Tests for weapon detection accuracy metrics."""

    def test_accuracy_above_90_percent(self, weapon_engine):
        """Weapon model accuracy should be >= 90%."""
        frames = _create_test_frames()
        predictions = []
        
        for sample in frames:
            weapon_engine.process_frame(sample["frame"])
            start_wait = time.time()
            while time.time() - start_wait < 5.0:
                signal = weapon_engine.latest_signal()
                if not signal.get("inferenceRunning", False):
                    break
                time.sleep(0.05)
            
            signal = weapon_engine.latest_signal()
            score = signal.get("score", 0.0)
            pred = 1 if score > 0.20 else 0
            predictions.append((sample["label"], pred))
        
        correct = sum(1 for true, pred in predictions if true == pred)
        accuracy = correct / len(predictions)
        assert accuracy >= 0.90, f"Accuracy {accuracy:.2%} is below 90% threshold"

    def test_precision_above_85_percent(self, weapon_engine):
        """Weapon model precision should be >= 85%."""
        frames = _create_test_frames()
        tp = fp = 0
        
        for sample in frames:
            weapon_engine.process_frame(sample["frame"])
            start_wait = time.time()
            while time.time() - start_wait < 5.0:
                signal = weapon_engine.latest_signal()
                if not signal.get("inferenceRunning", False):
                    break
                time.sleep(0.05)
            
            signal = weapon_engine.latest_signal()
            score = signal.get("score", 0.0)
            pred = 1 if score > 0.20 else 0
            
            if pred == 1 and sample["label"] == 1:
                tp += 1
            elif pred == 1 and sample["label"] == 0:
                fp += 1
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        assert precision >= 0.85, f"Precision {precision:.2%} is below 85% threshold"

    def test_recall_above_85_percent(self, weapon_engine):
        """Weapon model recall should be >= 85%."""
        frames = _create_test_frames()
        tp = fn = 0
        
        for sample in frames:
            weapon_engine.process_frame(sample["frame"])
            start_wait = time.time()
            while time.time() - start_wait < 5.0:
                signal = weapon_engine.latest_signal()
                if not signal.get("inferenceRunning", False):
                    break
                time.sleep(0.05)
            
            signal = weapon_engine.latest_signal()
            score = signal.get("score", 0.0)
            pred = 1 if score > 0.20 else 0
            
            if pred == 1 and sample["label"] == 1:
                tp += 1
            elif pred == 0 and sample["label"] == 1:
                fn += 1
        
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        assert recall >= 0.85, f"Recall {recall:.2%} is below 85% threshold"

    def test_f1_score_above_85_percent(self, weapon_engine):
        """Weapon model F1 score should be >= 85%."""
        frames = _create_test_frames()
        tp = fp = fn = 0
        
        for sample in frames:
            weapon_engine.process_frame(sample["frame"])
            start_wait = time.time()
            while time.time() - start_wait < 5.0:
                signal = weapon_engine.latest_signal()
                if not signal.get("inferenceRunning", False):
                    break
                time.sleep(0.05)
            
            signal = weapon_engine.latest_signal()
            score = signal.get("score", 0.0)
            pred = 1 if score > 0.20 else 0
            
            if pred == 1 and sample["label"] == 1:
                tp += 1
            elif pred == 1 and sample["label"] == 0:
                fp += 1
            elif pred == 0 and sample["label"] == 1:
                fn += 1
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        assert f1 >= 0.85, f"F1 score {f1:.2%} is below 85% threshold"


class TestWeaponInferenceLatency:
    """Tests for weapon inference performance."""

    def test_inference_latency_under_500ms(self, weapon_engine):
        """Single inference should complete under 500ms."""
        rng = np.random.RandomState(42)
        frame = rng.randint(30, 200, (480, 640, 3), dtype=np.uint8)
        
        weapon_engine.process_frame(frame)
        start_wait = time.time()
        while time.time() - start_wait < 10.0:
            signal = weapon_engine.latest_signal()
            if not signal.get("inferenceRunning", False):
                break
            time.sleep(0.05)
        
        signal = weapon_engine.latest_signal()
        latency = signal.get("inferenceLatencyMs", 0)
        assert latency < 500, f"Inference took {latency:.0f}ms, should be under 500ms"

    def test_inference_latency_under_200ms_avg(self, weapon_engine):
        """Average inference over 10 frames should be under 200ms."""
        rng = np.random.RandomState(42)
        latencies = []
        
        for _ in range(10):
            frame = rng.randint(30, 200, (480, 640, 3), dtype=np.uint8)
            weapon_engine.process_frame(frame)
            start_wait = time.time()
            while time.time() - start_wait < 10.0:
                signal = weapon_engine.latest_signal()
                if not signal.get("inferenceRunning", False):
                    break
                time.sleep(0.05)
            
            signal = weapon_engine.latest_signal()
            lat = signal.get("inferenceLatencyMs", 0)
            if lat > 0:
                latencies.append(lat)
        
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        assert avg_latency < 200, f"Average inference {avg_latency:.0f}ms should be under 200ms"


class TestWeaponScoreRange:
    """Tests for weapon score output validity."""

    def test_score_is_between_0_and_1(self, weapon_engine):
        """Weapon score should always be in [0, 1]."""
        rng = np.random.RandomState(42)
        for _ in range(10):
            frame = rng.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            weapon_engine.process_frame(frame)
            start_wait = time.time()
            while time.time() - start_wait < 5.0:
                signal = weapon_engine.latest_signal()
                if not signal.get("inferenceRunning", False):
                    break
                time.sleep(0.05)
            
            signal = weapon_engine.latest_signal()
            score = signal.get("score", 0.0)
            assert 0.0 <= score <= 1.0, f"Score {score} is outside [0, 1]"

    def test_non_weapon_frame_has_low_score(self, weapon_engine):
        """Non-weapon frames should produce low scores (< 0.50)."""
        rng = np.random.RandomState(123)
        frame = rng.randint(150, 220, (480, 640, 3), dtype=np.uint8)
        
        weapon_engine.process_frame(frame)
        start_wait = time.time()
        while time.time() - start_wait < 5.0:
            signal = weapon_engine.latest_signal()
            if not signal.get("inferenceRunning", False):
                break
            time.sleep(0.05)
        
        signal = weapon_engine.latest_signal()
        score = signal.get("score", 0.0)
        assert score < 0.50, f"Non-weapon frame score {score} is too high"


class TestWeaponEngineRobustness:
    """Tests for weapon engine robustness and edge cases."""

    def test_handles_black_frame(self, weapon_engine):
        """Engine should handle all-black frames without crashing."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        weapon_engine.process_frame(frame)
        time.sleep(0.5)
        signal = weapon_engine.latest_signal()
        assert signal["failed"] is False

    def test_handles_white_frame(self, weapon_engine):
        """Engine should handle all-white frames without crashing."""
        frame = np.full((480, 640, 3), 255, dtype=np.uint8)
        weapon_engine.process_frame(frame)
        time.sleep(0.5)
        signal = weapon_engine.latest_signal()
        assert signal["failed"] is False

    def test_handles_small_frame(self, weapon_engine):
        """Engine should handle very small frames."""
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        weapon_engine.process_frame(frame)
        time.sleep(0.5)
        signal = weapon_engine.latest_signal()
        assert signal["failed"] is False

    def test_handles_large_frame(self, weapon_engine):
        """Engine should handle large frames (1080p)."""
        rng = np.random.RandomState(42)
        frame = rng.randint(0, 255, (1080, 1920, 3), dtype=np.uint8)
        weapon_engine.process_frame(frame)
        time.sleep(1.0)
        signal = weapon_engine.latest_signal()
        assert signal["failed"] is False

    def test_consecutive_frames_consistent(self, weapon_engine):
        """Same frame should produce consistent scores across runs."""
        rng = np.random.RandomState(42)
        frame = rng.randint(30, 200, (480, 640, 3), dtype=np.uint8)
        
        scores = []
        for _ in range(3):
            weapon_engine.process_frame(frame)
            start_wait = time.time()
            while time.time() - start_wait < 5.0:
                signal = weapon_engine.latest_signal()
                if not signal.get("inferenceRunning", False):
                    break
                time.sleep(0.05)
            signal = weapon_engine.latest_signal()
            scores.append(signal.get("score", 0.0))
            time.sleep(0.3)
        
        score_range = max(scores) - min(scores)
        assert score_range < 0.30, f"Score variance {score_range:.3f} too high: {scores}"

    def test_reset_clears_state(self, weapon_engine):
        """Reset should clear engine state."""
        rng = np.random.RandomState(42)
        frame = rng.randint(30, 200, (480, 640, 3), dtype=np.uint8)
        weapon_engine.process_frame(frame)
        time.sleep(0.5)
        
        weapon_engine.reset()
        signal = weapon_engine.latest_signal()
        assert signal["score"] == 0.0
        assert signal["labels"] == []


class TestWeaponConfigValidation:
    """Tests for weapon configuration options."""

    def test_default_config(self):
        """Default config should have expected values."""
        from weapon import WeaponConfig
        config = WeaponConfig()
        assert config.enabled is True
        assert config.backend == "yolo"
        assert config.interval == 8
        assert config.min_confidence == 0.20
        assert config.labels == ("pistol", "rifle", "knife")

    def test_custom_confidence(self):
        """Custom confidence threshold should be respected."""
        from weapon import WeaponConfig
        config = WeaponConfig(min_confidence=0.50)
        assert config.min_confidence == 0.50

    def test_custom_labels(self):
        """Custom labels should be stored correctly."""
        from weapon import WeaponConfig
        config = WeaponConfig(labels=("gun", "blade"))
        assert config.labels == ("gun", "blade")

    def test_config_from_env(self):
        """Config should read from environment variables."""
        from weapon import WeaponConfig
        env = {"WEAPON_BACKEND": "yolo", "WEAPON_MIN_CONFIDENCE": "0.35", "WEAPON_LABELS": "pistol,knife"}
        config = WeaponConfig.from_settings({}, env=env)
        assert config.backend == "yolo"
        assert config.min_confidence == 0.35
        assert config.labels == ("pistol", "knife")

    def test_disabled_engine_skips_processing(self):
        """Disabled engine should not process frames."""
        import torch
        from weapon import WeaponConfig, WeaponSignalEngine
        config = WeaponConfig(enabled=False)
        engine = WeaponSignalEngine(config, device=torch.device("cpu"))
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        result = engine.process_frame(frame)
        assert result["enabled"] is False
        assert result["score"] == 0.0
