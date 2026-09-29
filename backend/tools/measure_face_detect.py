"""WT-21 measurement: YuNet face detection latency + capture fitness on
repository demo-clip fixture frames.

Scope (EXP-21-01/02/03): CPU latency distribution per resolution class
(cold vs warm separated), native vs 640-max-side detection counts, and
failure-state behavior (tiny face, motion blur, no face) including the
REPORTING gate. NOT an accuracy evaluation: the fixture set has no labeled
ground truth; counts are detection outputs, and any hand-verified subset is
labelled as such by the caller.

Run (measurement requires the campaign RESOURCE-LOCK):

    python backend/tools/measure_face_detect.py --fixtures assets/fixtures \
        --model assets/yunet/face_detection_yunet_2023mar.onnx --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from face_detect import YuNetFaceDetector, reporting_gate


def latency_stats(samples_ms: list[float]) -> dict:
    arr = np.asarray(samples_ms, dtype=np.float64)
    return {
        "n": int(arr.size),
        "p05_ms": round(float(np.percentile(arr, 5)), 3),
        "median_ms": round(float(np.median(arr)), 3),
        "p95_ms": round(float(np.percentile(arr, 95)), 3),
        "mean_ms": round(float(arr.mean()), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--json", default="")
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()

    detector = YuNetFaceDetector(model_path=args.model)
    frames = sorted(Path(args.fixtures).glob("*.jpg"))
    report: dict = {
        "model": str(args.model),
        "model_sha256": detector.health().get("model_sha256"),
        "fixture_frames": len(frames),
        "repeats": args.repeats,
        "source_mode": "file-media fixtures extracted from demo_assets/videos/*.avi (NOT live capture)",
    }

    # EXP-21-01/02: native detection + latency per resolution class,
    # and 640-max-side comparison (WT-22 ring geometry)
    latency_by_class: dict[str, list[float]] = {}
    native_faces = 0
    downscaled_faces = 0
    per_frame = []
    cold_ms = []
    for frame_path in frames:
        frame = cv2.imread(str(frame_path))
        height, width = frame.shape[:2]
        cls = f"{width}x{height}"
        # cold: first call on this frame after fresh input size
        t0 = time.perf_counter()
        faces = detector.detect(frame)
        cold_ms.append((time.perf_counter() - t0) * 1000.0)
        native_faces += len(faces)
        warm = []
        for _ in range(args.repeats):
            t0 = time.perf_counter()
            detector.detect(frame)
            warm.append((time.perf_counter() - t0) * 1000.0)
        latency_by_class.setdefault(cls, []).extend(warm)
        # 640-max-side (WT-22 scoring ring geometry)
        scale = min(1.0, 640 / max(width, height))
        small = cv2.resize(frame, (max(1, round(width * scale)), max(1, round(height * scale))),
                           interpolation=cv2.INTER_AREA)
        small_faces = detector.detect(small)
        downscaled_faces += len(small_faces)
        per_frame.append({
            "frame": frame_path.name, "size": cls,
            "faces_native": len(faces), "faces_max640": len(small_faces),
            "ied_px_native": [round(f.ied_px, 1) for f in faces],
            "yaw_proxy_deg": [round(f.yaw_proxy_deg, 1) for f in faces],
        })
        print(f"{frame_path.name} {cls} native={len(faces)} max640={len(small_faces)}")

    report["per_frame"] = per_frame
    report["totals"] = {
        "faces_native_all_frames": native_faces,
        "faces_max640_all_frames": downscaled_faces,
        "frames_with_faces_native": sum(1 for f in per_frame if f["faces_native"]),
        "frames_with_faces_max640": sum(1 for f in per_frame if f["faces_max640"]),
    }
    report["latency_warm_by_class"] = {cls: latency_stats(v) for cls, v in latency_by_class.items()}
    report["latency_cold_first_call_ms"] = latency_stats(cold_ms)

    # EXP-21-03: failure states on a face-positive frame, if one exists
    positive = next((p for p in per_frame if p["faces_native"] > 0), None)
    if positive is not None:
        frame_path = Path(args.fixtures) / positive["frame"]
        frame = cv2.imread(str(frame_path))
        source_faces = detector.detect(frame)
        x1, y1, x2, y2 = (int(round(v)) for v in source_faces[0].bbox_xyxy)
        face_crop = frame[y1:y2, x1:x2]
        states = {}
        # tiny face: shrink the frame so the face box falls below the gate
        tiny_frame = cv2.resize(frame, (frame.shape[1] // 6, frame.shape[0] // 6),
                                interpolation=cv2.INTER_AREA)
        tiny_faces = detector.detect(tiny_frame)
        states["tiny_face_frame_1_6_scale"] = {
            "detected": len(tiny_faces),
            "reportable": sum(1 for g in reporting_gate(tiny_faces) if g["reportable"]),
            "reasons": [r for g in reporting_gate(tiny_faces) for r in g["unreportable_reasons"]],
        }
        # motion blur on the face region
        blurred = frame.copy()
        ksize = 21
        blurred[y1:y2, x1:x2] = cv2.GaussianBlur(face_crop, (ksize, ksize), 8)
        blur_faces = detector.detect(blurred)
        states["motion_blur_face_region"] = {
            "detected": len(blur_faces),
            "reportable": sum(1 for g in reporting_gate(blur_faces) if g["reportable"]),
        }
        # no face: flat synthetic scene
        scene = np.full((480, 640, 3), 90, dtype=np.uint8)
        cv2.rectangle(scene, (100, 100), (400, 400), (30, 30, 30), -1)
        states["synthetic_no_face_scene"] = {"detected": len(detector.detect(scene))}
        report["failure_states"] = states

    text = json.dumps(report, indent=2)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
        print("wrote", args.json)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
