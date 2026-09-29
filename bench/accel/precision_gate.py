"""fp16 precision gate (WT-16, EXP-04, optional; REJECT on parity break).

The registered fp32 ONNX is the promotion reference. A naive whole-model fp16
candidate is produced with the SAME export path for both precisions
(ultralytics export from the operator's weapon checkpoint, copied read-only to
an untracked scratch dir; nothing is written next to user assets and no
multi-MB binary is committed). fp32-export vs fp16-export on CUDA EP isolates
the precision variable; export drift vs the registered ONNX is reported
separately and is not conflated with the precision comparison.

Mixed-precision conversion with detection-head block-listing (the ORT
`onnxconverter_common.float16` Mixed-Precision tool) is NOT runnable here: the
package is absent and the shared venv is read-only (no installs). That variant
is therefore deferred with reason, not silently dropped.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.accel.fixtures import load_frames  # noqa: E402
from bench.accel.harness import build_session  # noqa: E402
from bench.accel.parity import (CONFIDENCE, IOU_THRESHOLD, MAX_DETECTIONS,  # noqa: E402
                                match_decoded, near_threshold_flips)

SCRATCH = Path("C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-16-artifacts/fp16")
CHECKPOINT = Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/weapon_hadi_yolo.pt")
REGISTERED_WEAPON_ONNX = Path("C:/Users/PCD/Downloads/Final Project AI Sentinel/backend/models/weapon_yolo.onnx")


def _sha256(path: Path) -> str:
    import hashlib
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def export_variants(checkpoint: Path, scratch: Path) -> dict:
    scratch.mkdir(parents=True, exist_ok=True)
    local_checkpoint = scratch / checkpoint.name
    if not local_checkpoint.exists():
        shutil.copy2(checkpoint, local_checkpoint)
    export_script = (
        "import os; os.environ['YOLO_CONFIG_DIR'] = os.environ.get('YOLO_CONFIG_DIR', '');"
        "from ultralytics import YOLO;"
        f"model = YOLO(r'{local_checkpoint}');"
        "model.export(format='onnx', half=%s)"
    )
    produced = {}
    for label, half in (("fp32", "False"), ("fp16", "True")):
        completed = subprocess.run(
            [sys.executable, "-c", export_script % half],
            capture_output=True, text=True, cwd=str(scratch), timeout=600,
            env=dict(os.environ, YOLO_CONFIG_DIR=str(scratch / "ultralytics-config")))
        artifact = local_checkpoint.with_suffix(".onnx")
        target = scratch / f"weapon-export-{label}.onnx"
        if completed.returncode != 0 or not artifact.exists():
            produced[label] = {"ok": False, "stderr": completed.stderr[-2000:]}
        else:
            artifact.replace(target)
            produced[label] = {"ok": True, "path": str(target), "sha256": _sha256(target),
                               "bytes": target.stat().st_size,
                               "exportStdoutTail": completed.stdout[-500:]}
    produced["checkpointCopy"] = {"path": str(local_checkpoint), "sha256": _sha256(local_checkpoint)}
    return produced


def compare_models(reference: Path, candidate: Path, label: str) -> dict:
    """Raw + decoded parity between two ONNX files on CUDA EP (same inputs)."""
    import yolo_onnx
    frames, fixture_manifest = load_frames()
    ref_session, ref_providers, ref_load = build_session(reference, "cuda")
    cand_session, cand_providers, cand_load = build_session(candidate, "cuda")
    meta = ref_session.get_modelmeta()
    names = yolo_onnx.model_names(meta.custom_metadata_map)
    output_format = yolo_onnx.model_output_format(meta.custom_metadata_map)
    width, height = yolo_onnx.model_input_size(ref_session.get_inputs()[0].shape)
    pairs = [yolo_onnx.prepare_input(frame, (width, height)) for frame in frames]
    num_classes = len(names)
    raw_max_abs_diff, nonfinite = 0.0, 0
    matches, flips = [], {}
    for tensor, transform in pairs:
        ref_out = ref_session.run(None, {ref_session.get_inputs()[0].name: tensor})[0]
        cand_out = cand_session.run(None, {cand_session.get_inputs()[0].name: tensor})[0]
        nonfinite += int((~np.isfinite(cand_out)).sum())
        ref64, cand64 = ref_out.astype(np.float64), cand_out.astype(np.float64)
        raw_max_abs_diff = max(raw_max_abs_diff, float(np.max(np.abs(ref64 - cand64))))
        ref_rows = yolo_onnx.decode_detections(ref_out, num_classes=num_classes, transform=transform,
                                               confidence=CONFIDENCE, iou_threshold=IOU_THRESHOLD,
                                               output_format=output_format,
                                               max_detections=MAX_DETECTIONS)
        cand_rows = yolo_onnx.decode_detections(cand_out, num_classes=num_classes, transform=transform,
                                                confidence=CONFIDENCE, iou_threshold=IOU_THRESHOLD,
                                                output_format=output_format,
                                                max_detections=MAX_DETECTIONS)
        matches.append(match_decoded(ref_rows, cand_rows))
        for threshold, count in near_threshold_flips(ref_rows, cand_rows).items():
            flips[threshold] = flips.get(threshold, 0) + count
    union = sum(m["cpuDetections"] for m in matches) + sum(m["unmatchedCuda"] for m in matches)
    matched = sum(m["matched"] for m in matches)
    return {
        "comparison": label,
        "reference": {"path": str(reference), "sha256": _sha256(reference)},
        "candidate": {"path": str(candidate), "sha256": _sha256(candidate)},
        "fixture": fixture_manifest,
        "providers": {"reference": ref_providers, "candidate": cand_providers},
        "stageModelLoadMs": {"reference": round(ref_load, 3), "candidate": round(cand_load, 3)},
        "rawMaxAbsDiff": round(raw_max_abs_diff, 6),
        "candidateNonFiniteValues": nonfinite,
        "decoded": {"matched": matched, "matchRate": round(matched / union, 6) if union else 1.0,
                    "referenceDetections": sum(m["cpuDetections"] for m in matches),
                    "candidateDetections": sum(m["cudaDetections"] for m in matches)},
        "nearThresholdFlips": flips,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[2] / "bench/results/campaign-accel-2026-09-29/raw")
    parser.add_argument("--skip-export", action="store_true",
                        help="Compare already-exported artifacts in the scratch dir")
    args = parser.parse_args()
    result = {"experiment": "fp16-gate", "scratch": str(SCRATCH),
              "mixedPrecisionBlockListTooling": {
                  "onnxconverterCommon": "ABSENT in shared venv (read-only; no installs)",
                  "status": "deferred with reason: detection-head block-listing needs onnxconverter_common.float16"},
              "clockBase": "perf_counter"}
    if not args.skip_export:
        result["exports"] = export_variants(CHECKPOINT, SCRATCH)
    else:
        result["exports"] = {"skipped": True}
    fp32 = SCRATCH / "weapon-export-fp32.onnx"
    fp16 = SCRATCH / "weapon-export-fp16.onnx"
    if fp32.exists() and fp16.exists():
        result["fp32ExportVsFp16Export"] = compare_models(fp32, fp16, "fp32-export vs fp16-export (precision variable only)")
        if REGISTERED_WEAPON_ONNX.exists():
            result["registeredVsFp32Export"] = compare_models(REGISTERED_WEAPON_ONNX, fp32,
                                                              "registered weapon_yolo.onnx vs fp32 export (export drift)")
        gate = result["fp32ExportVsFp16Export"]
        adopt = (gate["candidateNonFiniteValues"] == 0
                 and gate["rawMaxAbsDiff"] <= 0.02
                 and gate["decoded"]["matchRate"] >= 0.98
                 and all(count == 0 for count in gate["nearThresholdFlips"].values()))
        result["verdict"] = ("adopt" if adopt else
                             "reject: naive whole-model fp16 breaks the parity gate; fp32 stays default")
    else:
        result["verdict"] = "inconclusive: fp16 export artifacts unavailable (see exports block)"
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "raw-fp16-gate.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    result["rawPath"] = str(path)
    print(json.dumps({key: result[key] for key in ("experiment", "verdict", "rawPath")}, indent=2))


if __name__ == "__main__":
    main()
