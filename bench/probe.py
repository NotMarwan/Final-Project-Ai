"""Read-only source/model probes and deterministic defect reproductions."""
from __future__ import annotations

import argparse
import ast
import asyncio
import gc
import time
from pathlib import Path

from bench.common import BACKEND, ROOT, distribution, environment, prepare_environment, sha256, write_json


def inspect_models():
    import onnxruntime as ort
    models = []
    for path in sorted(BACKEND.glob("*.pt")):
        models.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path)})
    for path in sorted((BACKEND / "models").glob("*.onnx")):
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        models.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
                       "sha256": sha256(path), "providers": session.get_providers(),
                       "inputs": [{"name": x.name, "shape": x.shape, "type": x.type} for x in session.get_inputs()],
                       "outputs": [{"name": x.name, "shape": x.shape} for x in session.get_outputs()],
                       "metadata": session.get_modelmeta().custom_metadata_map})
    return {"available_onnx_providers": ort.get_available_providers(), "models": models}


def inventory_clips():
    import cv2
    rows = []
    candidates = list((ROOT / "demo_assets" / "videos").glob("*.avi")) + list((ROOT / "samples").glob("*.mp4")) + list(BACKEND.glob("cam*.*"))
    for path in sorted(candidates):
        if path.suffix not in (".avi", ".mp4"):
            continue
        cap = cv2.VideoCapture(str(path))
        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            ret, frame = cap.read()
            rows.append({"path": str(path.relative_to(ROOT)), "sha256": sha256(path), "readable": bool(ret),
                         "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                         "nominal_fps": fps, "nominal_frames": count, "duration_seconds": count / fps if fps else None,
                         "label": "unknown", "label_verified": False, "source": "existing local project asset",
                         "license": "unverified", "event_onset_seconds": None})
        finally:
            cap.release()
    return rows


def source_audit():
    result = {"silent_handlers": [], "mutating_routes": [], "legacy_tests": []}
    for name in ("api", "inference", "inference_process", "weapon", "fusion", "pipeline_render", "pipeline_capture"):
        path = BACKEND / (name + ".py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                result["silent_handlers"].append({"file": str(path.relative_to(ROOT)), "line": node.lineno,
                                                    "exception": ast.unparse(node.type) if node.type else "bare"})
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr in ("post", "put", "patch", "delete"):
                        result["mutating_routes"].append({"function": node.name, "line": node.lineno,
                            "method": decorator.func.attr.upper(), "route": ast.literal_eval(decorator.args[0]),
                            "async": isinstance(node, ast.AsyncFunctionDef)})
    for path in sorted((BACKEND / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        result["legacy_tests"].append({"file": path.name, "test_functions": [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]})
    return result


def reproduce():
    import numpy as np
    import inference
    from collections import deque
    from frame_pipeline import OverlayCache
    from fusion import FusionConfig, ThreatFusionEngine
    from pipeline_render import RenderThread
    from weapon import WeaponConfig, WeaponSignalEngine

    calls = []
    resets = []
    class SpyDecision:
        cooldown_seconds = 3
        def update(self, score):
            calls.append(score)
            return {"confirmed_alert": False}
        def reset(self):
            resets.append(True)

    annotated = []
    cache = OverlayCache()
    renderer = RenderThread(deque(), cache, set_frame_fn=lambda *a: None,
                            annotate_fn=lambda **k: (annotated.append(True) or k["frame"]),
                            decision_layer=SpyDecision())
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    for value in (0.1, 0.8, 0.1, 0.1):
        cache.update(is_threat=value > .25, threat_confidence=value * 100)
        renderer._render_frame(frame)

    inference._frame_cache.clear()
    inference._frame_cache_keys.clear()
    reused = None
    # Real CPython allocator experiment. Failure to reproduce is recorded as such.
    for index in range(5000):
        sample = np.full((12, 12, 3), index % 251, dtype=np.uint8)
        observed = int(inference.cached_resize(sample, 24)[0, 0, 0])
        if observed != index % 251:
            reused = {"iteration": index, "expected_pixel": index % 251, "observed_pixel": observed}
            break
        del sample

    engine = WeaponSignalEngine(WeaponConfig(enabled=False))
    engine._update_score(best=.9, labels=["knife"], bbox=[.1, .1, .4, .4])
    initial = engine.latest_signal()
    engine._update_score(best=0, labels=[])
    after = engine.latest_signal()

    async def timer_probe():
        samples = []
        for _ in range(100):
            start = time.perf_counter()
            await asyncio.sleep(.005)
            samples.append((time.perf_counter() - start) * 1000)
        return distribution(samples)

    return {"D-01": {"input_scores": [.1, .8, .1, .1], "decision_scores_received": calls},
            "D-04": {"artifact_exists": (BACKEND / "model_calibration.json").exists()},
            "D-07": {"address_reuse_corruption": reused, "attempt_limit": 5000},
            "D-08": {"single_hit": initial, "first_no_hit": after,
                     "note": "Score lingers but bbox is cleared immediately on the first completed no-hit inference."},
            "D-09": ThreatFusionEngine(FusionConfig()).assess(violence_confidence=0, motion_score=0, weapon_score=0),
            "D-10": {"frames": 4, "annotated_frames": len(annotated)},
            "D-12": {"asyncio_sleep_requested_ms": 5, "actual_ms": asyncio.run(timer_probe())}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "bench/results/probe.json")
    args = parser.parse_args()
    settings = prepare_environment()
    payload = {"environment": environment(), "detection_environment": settings, "source_audit": source_audit(),
               "models": inspect_models(), "clips": inventory_clips(), "reproductions": reproduce()}
    write_json(args.output, payload)
    print(f"Probe saved: {args.output}")


if __name__ == "__main__":
    main()
