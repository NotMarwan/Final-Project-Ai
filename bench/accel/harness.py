"""Completed-inference timing harness (WT-16, EXP-01/EXP-02).

Measurement discipline (WT-09 section 9 protocol, BINDING measurement rules):
- Every recorded duration is a single-clock `time.perf_counter_ns()` diff.
- CUDA runs call `torch.cuda.synchronize()` before the stop stamp; ORT `run()`
  additionally returns host outputs (sync at fetch). Never launch timing.
- Cold (first 5 samples after session creation) and warm (rest) are separated.
- Pre/post-processing are measured in their own distributions, never merged
  into the compute distribution.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bench.accel.fixtures import load_frames  # noqa: E402

COLD_SAMPLES = 5
DEFAULT_WARM_SAMPLES = 300


def resolve_model(explicit: str | None, env_key: str, default_name: str) -> Path:
    if explicit:
        return Path(explicit)
    from_env = os.getenv(env_key)
    if from_env:
        return Path(from_env)
    return Path(__file__).resolve().parents[2] / "backend" / "models" / default_name


def _percentile(sorted_values: list[float], q: float) -> float:
    position = (len(sorted_values) - 1) * q
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def distribution(values: list[float]) -> dict:
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return {"count": 0, "p05": None, "p50": None, "p95": None, "max": None}
    return {"count": len(ordered), "p05": round(_percentile(ordered, .05), 6),
            "p50": round(_percentile(ordered, .5), 6), "p95": round(_percentile(ordered, .95), 6),
            "max": round(ordered[-1], 6)}


def build_session(model_path: Path, device: str):
    """Create an ORT session through the production provider/session policy.

    CUDA EP sessions require torch's CUDA/cuDNN DLLs to be loaded in-process
    first (ORT "Preload DLLs" / "Compatibility with PyTorch" pattern): without
    them ORT fails with "CUDA_PATH is set but CUDA wasnt able to be loaded".
    The production inference worker satisfies this because inference.py imports
    torch before any session is created; the harness replicates that state.
    """
    import onnxruntime as ort
    import yolo_onnx
    providers = yolo_onnx.select_providers(ort, device)
    if device == "cuda":
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("device=cuda but torch reports no CUDA device (DLL preload check)")
        torch.cuda.init()
        torch.backends.cudnn.version()  # force cuDNN 8 DLL load before ORT binds it
    started = time.perf_counter_ns()
    session = ort.InferenceSession(str(model_path), sess_options=yolo_onnx.session_options(ort),
                                   providers=providers)
    load_ms = (time.perf_counter_ns() - started) / 1e6
    return session, providers, load_ms


def timed_inference(session, tensors: list, device: str, warm_samples: int = DEFAULT_WARM_SAMPLES,
                    sync_fn=None) -> dict:
    """Completed-inference timing: n = COLD_SAMPLES + warm_samples."""
    import onnxruntime as ort  # noqa: F401  (documents the runtime under test)
    if device == "cuda" and sync_fn is None:
        import torch
        if torch.cuda.is_available():
            def sync_fn():
                torch.cuda.synchronize()
        else:
            raise RuntimeError("device=cuda but torch reports no CUDA device for synchronization")
    input_name = session.get_inputs()[0].name
    output_names = [output.name for output in session.get_outputs()]
    records = []
    total = COLD_SAMPLES + warm_samples
    for sample in range(total):
        tensor = tensors[sample % len(tensors)]
        started = time.perf_counter_ns()
        session.run(output_names, {input_name: tensor})
        if sync_fn is not None:
            sync_fn()
        elapsed_ms = (time.perf_counter_ns() - started) / 1e6
        records.append({
            "sample": sample,
            "phase": "cold" if sample < COLD_SAMPLES else "warm",
            "stageInferenceComputeMs": round(elapsed_ms, 6),
            "inferenceComputeSynced": True,
            "cudaSyncApplied": sync_fn is not None,
        })
    cold = [r["stageInferenceComputeMs"] for r in records if r["phase"] == "cold"]
    warm = [r["stageInferenceComputeMs"] for r in records if r["phase"] == "warm"]
    return {
        "clockBase": "perf_counter",
        "timingSemantics": "completed-inference (ORT run returns host outputs; "
                           "CUDA runs add torch.cuda.synchronize() before the stop stamp)",
        "samples": records,
        "cold": {**distribution(cold), "definition": "first 5 samples after session creation"},
        "warm": {**distribution(warm), "definition": "samples 6..N"},
        "all": distribution([r["stageInferenceComputeMs"] for r in records]),
    }


def timed_preprocess(frames: list, size: tuple[int, int], iterations: int) -> dict:
    import yolo_onnx
    records = []
    for i in range(iterations):
        frame = frames[i % len(frames)]
        started = time.perf_counter_ns()
        yolo_onnx.prepare_input(frame, size)
        records.append(round((time.perf_counter_ns() - started) / 1e6, 6))
    return {"stagePreprocessMs": distribution(records),
            "timingSemantics": "letterbox+color convert+normalize, single clock"}


def timed_postprocess(outputs: list, *, num_classes: int, transforms: list, confidence: float,
                      classes: set[int] | None, iterations: int) -> dict:
    import yolo_onnx
    records = []
    for i in range(iterations):
        output = outputs[i % len(outputs)]
        transform = transforms[i % len(transforms)]
        started = time.perf_counter_ns()
        yolo_onnx.decode_detections(output, num_classes=num_classes, transform=transform,
                                    confidence=confidence, classes=classes)
        records.append(round((time.perf_counter_ns() - started) / 1e6, 6))
    return {"stagePostprocessMs": distribution(records),
            "timingSemantics": "raw decode + class-aware greedy NMS + border clip, single clock"}


def run_model_benchmark(model_label: str, model_path: Path, device: str, warm_samples: int,
                        video: Path | None, out_dir: Path, confidence: float = 0.25,
                        classes: set[int] | None = None) -> dict:
    import onnxruntime as ort  # noqa: F401
    import yolo_onnx
    frames, fixture_manifest = load_frames(video)
    session, providers, load_ms = build_session(model_path, device)
    meta = session.get_modelmeta()
    names = yolo_onnx.model_names(meta.custom_metadata_map)
    output_format = yolo_onnx.model_output_format(meta.custom_metadata_map)
    width, height = yolo_onnx.model_input_size(session.get_inputs()[0].shape)
    pairs = [yolo_onnx.prepare_input(frame, (width, height)) for frame in frames]
    tensors = [pair[0] for pair in pairs]
    transforms = [pair[1] for pair in pairs]

    # First completed inference: cold-start stage (bench process scope).
    first_started = time.perf_counter_ns()
    input_name = session.get_inputs()[0].name
    output_names = [output.name for output in session.get_outputs()]
    first_output = session.run(output_names, {input_name: tensors[0]})
    if device == "cuda":
        import torch
        torch.cuda.synchronize()
    first_inference_ms = (time.perf_counter_ns() - first_started) / 1e6

    timing = timed_inference(session, tensors, device, warm_samples)
    preprocess = timed_preprocess(frames, (width, height), warm_samples)
    num_classes = len(names)
    outputs = [session.run(output_names, {input_name: tensor})[0] for tensor in tensors]
    postprocess = timed_postprocess(outputs, num_classes=num_classes, transforms=transforms,
                                    confidence=confidence, classes=classes,
                                    iterations=warm_samples)
    result = {
        "experimentModel": model_label,
        "modelPath": str(model_path),
        "modelSha256": _sha256(model_path),
        "device": device,
        "providers": [entry if isinstance(entry, str) else list(entry) for entry in providers],
        "ortActiveProviders": session.get_providers(),
        "ortVersion": ort.__version__,
        "inputSize": [width, height],
        "numClasses": num_classes,
        "classNames": {str(k): v for k, v in names.items()},
        "outputFormat": output_format,
        "confidenceThreshold": confidence,
        "classFilter": sorted(classes) if classes is not None else "all",
        "fixture": fixture_manifest,
        "stageModelLoadMs": round(load_ms, 3),
        "stageFirstInferenceMs": round(first_inference_ms, 3),
        "inferenceColdStartMs": round(load_ms + first_inference_ms, 3),
        "coldStartScope": "bench process: model load -> first completed inference (excludes process spawn)",
        "completedInference": timing,
        "preprocess": preprocess,
        "postprocess": postprocess,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"raw-{model_label}-{device}.json"
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return {"rawPath": str(path), "warm": timing["warm"], "cold": timing["cold"],
            "stageModelLoadMs": result["stageModelLoadMs"],
            "stageFirstInferenceMs": result["stageFirstInferenceMs"]}


def _sha256(path: Path) -> str:
    import hashlib
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("person", "weapon"), required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--samples", type=int, default=DEFAULT_WARM_SAMPLES)
    parser.add_argument("--video", type=Path, default=None)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[2] / "bench/results/campaign-accel-2026-09-29/raw")
    parser.add_argument("--person-model", type=Path, default=None)
    parser.add_argument("--weapon-model", type=Path, default=None)
    args = parser.parse_args()
    if args.samples < 300:
        parser.error("protocol requires n>=300 warm samples per model per config")
    if args.model == "person":
        model_path = resolve_model(args.person_model, "AI_SENTINEL_PERSON_ONNX", "person_yolo.onnx")
        classes = None  # parity covers the full COCO-80 head
    else:
        model_path = resolve_model(args.weapon_model, "AI_SENTINEL_WEAPON_ONNX", "weapon_yolo.onnx")
        classes = None
    summary = run_model_benchmark(args.model, model_path.resolve(), args.device, args.samples,
                                  args.video, args.out, classes=classes)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
