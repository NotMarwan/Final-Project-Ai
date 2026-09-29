"""CPU-vs-CUDA output parity harness (WT-16, EXP-02 parity gate).

Both execution providers run the SAME ONNX bytes (hash recorded) on the SAME
prepared input tensors (built once, shared by reference). Two gates per model:

1. Raw tensor parity: max abs diff over the full output tensor.
2. Decoded parity at fixed NMS (conf 0.25, IoU 0.5, max_det 300): greedy
   same-class matching, match rate, matched IoU, score drift, plus the
   near-threshold flip count at the decision thresholds 0.45/0.55.

Any fp16 candidate must pass this same harness against the fp32 reference
before it can be considered for promotion (WT-09 section 8, R-02).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.accel.fixtures import load_frames  # noqa: E402
from bench.accel.harness import build_session, resolve_model  # noqa: E402

CONFIDENCE = 0.25
IOU_THRESHOLD = 0.5
MAX_DETECTIONS = 300
DECISION_THRESHOLDS = (0.45, 0.55)


def _box_iou(a: np.ndarray, b: np.ndarray) -> float:
    inter_w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    inter_h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = inter_w * inter_h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match_decoded(cpu_rows: np.ndarray, cuda_rows: np.ndarray, iou_floor: float = 0.5) -> dict:
    """Greedy same-class matching by descending CPU score; deterministic."""
    cpu_rows = cpu_rows[np.argsort(-cpu_rows[:, 4], kind="stable")]
    cuda_rows = cuda_rows[np.argsort(-cuda_rows[:, 4], kind="stable")]
    used = set()
    matched_ious, score_diffs, unmatched_cpu, unmatched_cuda = [], [], 0, 0
    for row in cpu_rows:
        best_iou, best_index = 0.0, None
        for index, candidate in enumerate(cuda_rows):
            if index in used or candidate[5] != row[5]:
                continue
            iou = _box_iou(row[:4], candidate[:4])
            if iou > best_iou:
                best_iou, best_index = iou, index
        if best_index is not None and best_iou >= iou_floor:
            used.add(best_index)
            matched_ious.append(best_iou)
            score_diffs.append(abs(float(row[4]) - float(cuda_rows[best_index][4])))
        else:
            unmatched_cpu += 1
    unmatched_cuda = len(cuda_rows) - len(used)
    union = len(cpu_rows) + unmatched_cuda
    return {
        "cpuDetections": int(len(cpu_rows)),
        "cudaDetections": int(len(cuda_rows)),
        "matched": len(matched_ious),
        "unmatchedCpu": unmatched_cpu,
        "unmatchedCuda": unmatched_cuda,
        "matchRate": round(len(matched_ious) / union, 6) if union else 1.0,
        "matchedIouMean": round(float(np.mean(matched_ious)), 6) if matched_ious else None,
        "matchedIouMin": round(float(np.min(matched_ious)), 6) if matched_ious else None,
        "matchedScoreAbsDiffMax": round(max(score_diffs), 6) if score_diffs else None,
    }


def near_threshold_flips(cpu_rows: np.ndarray, cuda_rows: np.ndarray) -> dict:
    flips = {}
    for threshold in DECISION_THRESHOLDS:
        cpu_above = {(round(float(r[0]), 1), round(float(r[1]), 1), int(r[5])) for r in cpu_rows if r[4] >= threshold}
        cuda_above = {(round(float(r[0]), 1), round(float(r[1]), 1), int(r[5])) for r in cuda_rows if r[4] >= threshold}
        flips[str(threshold)] = len(cpu_above.symmetric_difference(cuda_above))
    return flips


def _file_sha256(path: Path) -> str:
    import hashlib
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parity_for_model(model_label: str, model_path: Path, video: Path | None,
                     class_filter: set[int] | None) -> dict:
    import yolo_onnx
    frames, fixture_manifest = load_frames(video)
    cpu_session, cpu_providers, cpu_load_ms = build_session(model_path, "cpu")
    cuda_session, cuda_providers, cuda_load_ms = build_session(model_path, "cuda")
    meta = cpu_session.get_modelmeta()
    names = yolo_onnx.model_names(meta.custom_metadata_map)
    output_format = yolo_onnx.model_output_format(meta.custom_metadata_map)
    width, height = yolo_onnx.model_input_size(cpu_session.get_inputs()[0].shape)
    pairs = [yolo_onnx.prepare_input(frame, (width, height)) for frame in frames]
    num_classes = len(names)

    raw_max_abs_diff = 0.0
    raw_per_input = []
    decoded_matches, decoded_filtered_matches = [], []
    flips_all = {}
    for index, (tensor, transform) in enumerate(pairs):
        cpu_out = cpu_session.run(None, {cpu_session.get_inputs()[0].name: tensor})[0]
        cuda_out = cuda_session.run(None, {cuda_session.get_inputs()[0].name: tensor})[0]
        if cpu_out.shape != cuda_out.shape:
            raise AssertionError(f"output shape mismatch on input {index}: {cpu_out.shape} vs {cuda_out.shape}")
        diff = float(np.max(np.abs(cpu_out.astype(np.float64) - cuda_out.astype(np.float64))))
        raw_max_abs_diff = max(raw_max_abs_diff, diff)
        raw_per_input.append({"input": index, "maxAbsDiff": round(diff, 9)})
        cpu_rows = yolo_onnx.decode_detections(cpu_out, num_classes=num_classes, transform=transform,
                                               confidence=CONFIDENCE, iou_threshold=IOU_THRESHOLD,
                                               output_format=output_format,
                                               max_detections=MAX_DETECTIONS)
        cuda_rows = yolo_onnx.decode_detections(cuda_out, num_classes=num_classes, transform=transform,
                                                confidence=CONFIDENCE, iou_threshold=IOU_THRESHOLD,
                                                output_format=output_format,
                                                max_detections=MAX_DETECTIONS)
        decoded_matches.append(match_decoded(cpu_rows, cuda_rows))
        for threshold, count in near_threshold_flips(cpu_rows, cuda_rows).items():
            flips_all[threshold] = flips_all.get(threshold, 0) + count
        if class_filter is not None:
            cpu_f = yolo_onnx.decode_detections(cpu_out, num_classes=num_classes, transform=transform,
                                                confidence=CONFIDENCE, classes=class_filter,
                                                iou_threshold=IOU_THRESHOLD, output_format=output_format,
                                                max_detections=MAX_DETECTIONS)
            cuda_f = yolo_onnx.decode_detections(cuda_out, num_classes=num_classes, transform=transform,
                                                 confidence=CONFIDENCE, classes=class_filter,
                                                 iou_threshold=IOU_THRESHOLD, output_format=output_format,
                                                 max_detections=MAX_DETECTIONS)
            decoded_filtered_matches.append(match_decoded(cpu_f, cuda_f))

    def aggregate(matches: list[dict]) -> dict:
        totals = {key: sum(m[key] for m in matches) for key in
                  ("cpuDetections", "cudaDetections", "matched", "unmatchedCpu", "unmatchedCuda")}
        union = totals["cpuDetections"] + totals["unmatchedCuda"]
        ious = [m["matchedIouMean"] for m in matches if m["matchedIouMean"] is not None]
        return {**totals,
                "matchRate": round(totals["matched"] / union, 6) if union else 1.0,
                "matchedIouMeanOfMeans": round(float(np.mean(ious)), 6) if ious else None,
                "matchedIouMin": min((m["matchedIouMin"] for m in matches if m["matchedIouMin"] is not None),
                                     default=None),
                "matchedScoreAbsDiffMax": max((m["matchedScoreAbsDiffMax"] for m in matches
                                               if m["matchedScoreAbsDiffMax"] is not None), default=None)}

    return {
        "experimentModel": model_label,
        "modelPath": str(model_path),
        "modelSha256": _file_sha256(model_path),
        "fixture": fixture_manifest,
        "inputSize": [width, height],
        "numClasses": num_classes,
        "outputFormat": output_format,
        "nmsParams": {"confidence": CONFIDENCE, "iouThreshold": IOU_THRESHOLD,
                      "maxDetections": MAX_DETECTIONS, "space": "model space before border clipping"},
        "cpuProviders": cpu_providers,
        "cudaProviders": cuda_providers,
        "cpuActiveProviders": cpu_session.get_providers(),
        "cudaActiveProviders": cuda_session.get_providers(),
        "stageModelLoadMs": {"cpu": round(cpu_load_ms, 3), "cuda": round(cuda_load_ms, 3)},
        "rawParity": {"maxAbsDiff": round(raw_max_abs_diff, 9), "perInput": raw_per_input},
        "decodedParityAllClasses": aggregate(decoded_matches),
        "decodedParityClassFilter": (aggregate(decoded_filtered_matches)
                                     if decoded_filtered_matches else None),
        "nearThresholdFlipsAtDecisionThresholds": flips_all,
        "clockBase": "perf_counter",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("person", "weapon", "both"), default="both")
    parser.add_argument("--video", type=Path, default=None)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[2] / "bench/results/campaign-accel-2026-09-29/raw")
    parser.add_argument("--person-model", type=Path, default=None)
    parser.add_argument("--weapon-model", type=Path, default=None)
    parser.add_argument("--suffix", default="")
    args = parser.parse_args()
    jobs = []
    if args.model in ("person", "both"):
        jobs.append(("person", resolve_model(args.person_model, "AI_SENTINEL_PERSON_ONNX", "person_yolo.onnx"),
                     {0}))  # person COCO-80 head, production filter is class 0
    if args.model in ("weapon", "both"):
        jobs.append(("weapon", resolve_model(args.weapon_model, "AI_SENTINEL_WEAPON_ONNX", "weapon_yolo.onnx"),
                     None))  # full 6-class weapon head
    args.out.mkdir(parents=True, exist_ok=True)
    for label, model_path, class_filter in jobs:
        result = parity_for_model(label, model_path.resolve(), args.video, class_filter)
        path = args.out / f"raw-parity-{label}{args.suffix}.json"
        path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        summary = {"rawPath": str(path), "rawParity": result["rawParity"]["maxAbsDiff"],
                   "decoded": result["decodedParityAllClasses"],
                   "filtered": result["decodedParityClassFilter"],
                   "flips": result["nearThresholdFlipsAtDecisionThresholds"]}
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
