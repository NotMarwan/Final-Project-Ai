"""Real-time performance metrics for the video pipeline."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque


@dataclass
class PipelineMetrics:
    capture_fps: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    inference_latency_ms: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    encode_latency_ms: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    stream_fps: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    weapon_score: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    person_count: Deque[int] = field(default_factory=lambda: deque(maxlen=60))

    def record_capture(self, fps: float):
        self.capture_fps.append(fps)

    def record_inference(self, latency_ms: float):
        self.inference_latency_ms.append(latency_ms)

    def record_encode(self, latency_ms: float):
        self.encode_latency_ms.append(latency_ms)

    def record_stream(self, fps: float):
        self.stream_fps.append(fps)

    def record_weapon(self, score: float):
        self.weapon_score.append(score)

    def record_person(self, count: int):
        self.person_count.append(count)

    def summary(self) -> dict:
        def avg(d: Deque) -> float:
            return sum(d) / len(d) if d else 0.0
        return {
            "captureFps": round(avg(self.capture_fps), 1),
            "inferenceLatencyMs": round(avg(self.inference_latency_ms), 1),
            "encodeLatencyMs": round(avg(self.encode_latency_ms), 1),
            "streamFps": round(avg(self.stream_fps), 1),
            "avgWeaponScore": round(avg(self.weapon_score), 3),
            "avgPersonCount": round(avg(self.person_count), 1),
        }


pipeline_metrics = PipelineMetrics()
