"""Instrument the unchanged legacy runtime in a disposable localhost process.

Wrappers measure calls without changing thresholds, queues, or model scheduling.
The two deliberate differences are isolated storage and disabled external sinks.
"""
from __future__ import annotations

import argparse
import functools
import json
import multiprocessing as mp
import os
import queue
import threading
import time
from pathlib import Path

from bench.common import BACKEND, ROOT, prepare_environment, write_json

EVENTS = []
LOCK = threading.Lock()
FLUSH_LOCK = threading.Lock()
MODELS = {}
OUTPUT = None
TRACE_CHUNK = 0


def event(stage, started=None, **fields):
    now = time.perf_counter()
    with LOCK:
        EVENTS.append({"stage": stage, "at": now, "ms": (now - started) * 1000 if started is not None else None, **fields})


def flush():
    global TRACE_CHUNK
    if OUTPUT is not None:
        with FLUSH_LOCK:
            chunked = os.environ.get("SENTINEL_BENCH_CHUNK_TRACES") == "1"
            with LOCK:
                snapshot = list(EVENTS)
                if chunked:
                    EVENTS.clear()
            if chunked and not snapshot:
                return
            filename = (f"trace-{os.getpid()}-{TRACE_CHUNK:06d}.json" if chunked
                        else f"trace-{os.getpid()}.json")
            try:
                write_json(OUTPUT / filename, {"models": MODELS, "events": snapshot})
            except Exception:
                if chunked:
                    with LOCK:
                        EVENTS[:0] = snapshot
                raise
            if chunked:
                TRACE_CHUNK += 1


def checkpoint_trace():
    def save_periodically():
        while True:
            time.sleep(3)
            flush()
    threading.Thread(target=save_periodically, daemon=True).start()


def benchmark_models_ready(output: Path, all_detection: bool) -> bool:
    """Wait until the inference worker has loaded the models used by this run."""
    marker = output / "models-ready.json"
    try:
        ready = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    loaded = set(ready.get("loaded_models", []))
    required = {"violence", "weapon"} if all_detection else {"violence"}
    return ready.get("ready") is True and required <= loaded


class WorkerReadyEventProbe:
    """Write a single readiness marker after the worker finishes model setup."""
    def __init__(self, wrapped, all_detection: bool):
        self.wrapped = wrapped
        self.all_detection = all_detection

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    def set(self, *args, **kwargs):
        result = self.wrapped.set(*args, **kwargs)
        loaded_models = ["violence"]
        if self.all_detection:
            loaded_models.append("weapon")
        write_json(OUTPUT / "models-ready.json", {
            "ready": True,
            "loaded_models": loaded_models,
        })
        event("models_ready", loaded_models=loaded_models)
        return result


def timed(cls, method, stage):
    original = getattr(cls, method)
    @functools.wraps(original)
    def call(self, *args, **kwargs):
        start = time.perf_counter()
        success = False
        try:
            result = original(self, *args, **kwargs)
            success = True
            return result
        finally:
            event(stage, start, returned=success)
    setattr(cls, method, call)


class FrameQueueProbe:
    """Keep original payload intact. Byte count is accepted raw bytes, not wire bytes."""
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def put_nowait(self, frame):
        start = time.perf_counter()
        try:
            result = self.wrapped.put_nowait(frame)
            event("ipc_enqueue", start, bytes=frame.nbytes)
            return result
        except queue.Full:
            event("ipc_drop", start, bytes=frame.nbytes)
            raise

    def get_nowait(self):
        return self.get(block=False)

    def close(self):
        return self.wrapped.close()

    def cancel_join_thread(self):
        return self.wrapped.cancel_join_thread()

    def get(self, *args, **kwargs):
        result = self.wrapped.get(*args, **kwargs)
        event("ipc_receive", bytes=result.nbytes)
        return result


class ResultQueueProbe:
    """Record the source timestamps that accompany completed observations."""
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    def put(self, result, *args, **kwargs):
        if isinstance(result, dict):
            event("inference_result", inference_sequence=result.get("inference_sequence"),
                  frame_idx=result.get("frame_idx"),
                  capture_timestamp=result.get("violence_capture_timestamp", result.get("capture_timestamp")),
                  inference_sample_time=result.get("inference_sample_time"))
        return self.wrapped.put(result, *args, **kwargs)


def instrumented_worker(frame_queue, result_queue, stop_event, config):
    global OUTPUT
    OUTPUT = Path(os.environ["SENTINEL_BENCH_OUTPUT"])
    checkpoint_trace()
    prepare_environment()
    if os.environ.get("SENTINEL_BENCH_ALL_DETECTION") == "1":
        os.environ["PERSON_OVERLAY_ENABLED"] = "true"
    import inference
    import weapon
    import person_detector
    from inference_process import inference_worker

    original_init = inference.ViolenceInferencePipeline.__init__
    def violence_init(self, *args, **kwargs):
        started = time.perf_counter()
        original_init(self, *args, **kwargs)
        MODELS["violence"] = {"enabled": self.enabled, "device": str(self.device),
            "is_x3d_flag": self.is_x3d, "actual_model_class": type(self.model).__name__,
            "disabled_reason": self.disabled_reason, "stride": self.stride,
            "threshold": self.threshold, "load_ms": (time.perf_counter() - started) * 1000,
            "warmup_ms": getattr(self, "warmup_ms", 0.0),
            "inference_optimizations": {
                "cudnn_benchmark": inference.VIOLENCE_CUDNN_BENCHMARK and self.device.type == "cuda",
                "channels_last_3d": inference.VIOLENCE_CHANNELS_LAST_3D and self.device.type == "cuda",
                "pinned_host_tensor": inference.VIOLENCE_PINNED_HOST_TENSOR and self.device.type == "cuda",
                "fp16_autocast": inference.VIOLENCE_FP16_AUTOCAST and self.device.type == "cuda",
                "preprocess_workers": inference.SLOWFAST_PREPROCESS_WORKERS,
            }}
        event("violence_load", started, enabled=self.enabled)
        if self.model is not None:
            MODELS["violence"]["module_types"] = sorted({type(m).__name__ for m in self.model.modules()})
    inference.ViolenceInferencePipeline.__init__ = violence_init

    original_window = inference.ViolenceInferencePipeline._infer_window_async
    def window(self, frames, *args, **kwargs):
        start = time.perf_counter()
        original_window(self, frames, *args, **kwargs)
        # Original implementation reads tensor.item(), synchronizing the result.
        event("violence_window", start, score=self._last_conf, raw_score=self._last_raw_conf)
    inference.ViolenceInferencePipeline._infer_window_async = window

    original_weapon = weapon.WeaponSignalEngine._infer_async
    def weapon_call(self, frame, *args, **kwargs):
        start = time.perf_counter()
        original_weapon(self, frame, *args, **kwargs)
        signal = self.latest_signal()
        MODELS["weapon"] = {"actual_backend": type(self._backend).__name__, "config": self.config.__dict__,
                            "ready": signal["ready"], "failed": signal["failed"], "reason": signal["reason"]}
        if hasattr(self._backend, "session"):
            MODELS["weapon"]["providers"] = self._backend.session.get_providers()
        event("weapon_window", start, score=signal["score"], ready=signal["ready"], reason=signal["reason"])
    weapon.WeaponSignalEngine._infer_async = weapon_call
    timed(person_detector.PersonDetector, "detect", "person_call")
    timed(person_detector.PersonDetector, "_detect_onnx", "person_onnx")
    timed(person_detector.PersonDetector, "_detect_yolo", "person_yolo")
    if config.get("ready_event") is not None:
        config["ready_event"] = WorkerReadyEventProbe(
            config["ready_event"],
            all_detection=os.environ.get("SENTINEL_BENCH_ALL_DETECTION") == "1",
        )
    try:
        inference_worker(frame_queue, ResultQueueProbe(result_queue), stop_event, config)
    finally:
        flush()


def install_benchmark_adapters():
    """Disable unrelated optional services missing from an isolated replay checkout."""
    import importlib.util
    import sys
    import types

    adapters = []
    if "go2rtc_bridge" not in sys.modules and importlib.util.find_spec("go2rtc_bridge") is None:
        module = types.ModuleType("go2rtc_bridge")

        class DisabledGo2RTCBridge:
            is_running = False

            def __init__(self, *_args, **_kwargs):
                pass

            def start(self):
                self.is_running = False

            def stop(self):
                self.is_running = False

            def get_whep_url(self, _camera_id):
                return None

            def proxy_whep(self, *_args, **_kwargs):
                return 503, b""

            def proxy_ice(self, *_args, **_kwargs):
                return 503, b""

        module.Go2RTCBridge = DisabledGo2RTCBridge
        sys.modules[module.__name__] = module
        adapters.append(module.__name__)

    if ("openrouter_reporting" not in sys.modules and
            importlib.util.find_spec("openrouter_reporting") is None):
        module = types.ModuleType("openrouter_reporting")

        class DisabledDeepSeekReportService:
            def __init__(self, *_args, **_kwargs):
                pass

            def status(self):
                return {"enabled": False, "available": False, "reason": "Disabled in isolated benchmark"}

            def demo_alert(self):
                raise RuntimeError("Reporting is disabled in isolated benchmark")

            def generate(self, *_args, **_kwargs):
                raise RuntimeError("Reporting is disabled in isolated benchmark")

            def get_cached(self, _alert_id):
                return None

        module.DeepSeekReportService = DisabledDeepSeekReportService
        sys.modules[module.__name__] = module
        adapters.append(module.__name__)

    return adapters


def configure(output, source, all_detection):
    global OUTPUT
    OUTPUT = output
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_trace()
    os.environ["SENTINEL_BENCH_OUTPUT"] = str(output)
    prepare_environment()
    if all_detection:
        os.environ["SENTINEL_BENCH_ALL_DETECTION"] = "1"
        os.environ["PERSON_OVERLAY_ENABLED"] = "true"
    adapters = install_benchmark_adapters()
    write_json(output / "benchmark-overrides.json", {
        "disabled_optional_modules": adapters,
        "reason": "These optional services are outside the local replay capture-to-alert workload.",
    })
    # Both parent and child resolve the same relative checkpoint paths.
    os.chdir(BACKEND)
    import api
    import inference_process
    import pipeline_capture
    import pipeline_render
    import security
    import temporal_frames
    import uvicorn

    api.config["notifications"]["telegram"]["enabled"] = False
    api.config["face_intel"]["enabled"] = False
    for key in ("thumbnails_dir", "evidence_dir", "reports_dir"):
        api.config["storage"][key] = str(output / key)
    api.config["security"]["audit_log_path"] = str(output / "audit.jsonl")
    api.config["security"]["api_key"] = "local-benchmark-only"
    os.environ["ADMIN_API_KEY"] = "local-benchmark-only"
    api.config["storage"]["evidence_ledger_path"] = str(output / "evidence-ledger.jsonl")
    for name, subdir in (("EVIDENCE_DIR", "evidence_dir"), ("THUMBNAILS_DIR", "thumbnails_dir"), ("REPORTS_DIR", "reports_dir")):
        path = output / subdir
        path.mkdir(exist_ok=True)
        setattr(api, name, path)
    api.CAMERA_SOURCES = {"BENCH": source}
    api.DEFAULT_CAMERA_ID = "BENCH"
    api.EXAMPLE_SOURCES = {}
    api.CAPTURE_LOOP_ENABLED = True
    os.environ["ACTIVE_CAMERAS"] = "BENCH"

    original_read = pipeline_capture.CaptureThread.read_frame
    def read(self):
        start = time.perf_counter()
        result = original_read(self)
        event("capture", start, ok=result[0], bytes=result[1].nbytes if result[0] else 0)
        return result
    pipeline_capture.CaptureThread.read_frame = read

    original_packet_init = temporal_frames.FramePacket.__init__
    def packet_init(self, *args, **kwargs):
        original_packet_init(self, *args, **kwargs)
        event("frame_packet", sequence=self.sequence, capture_timestamp=self.captured_at)
    temporal_frames.FramePacket.__init__ = packet_init

    original_render_init = pipeline_render.RenderThread.__init__
    def render_init(self, *args, **kwargs):
        original_render_init(self, *args, **kwargs)
        self._bench_decision_contexts = {}
        self._bench_alert_context = None
        original_on_threat = self.on_threat_fn
        if original_on_threat is not None:
            def on_threat(payload, *callback_args, **callback_kwargs):
                context = self._bench_alert_context or {}
                event("alert_decision", at=context.get("decision_at", time.perf_counter()),
                      alert_id=payload.get("id"),
                      capture_timestamp=context.get("capture_timestamp"),
                      inference_sequence=context.get("inference_sequence"),
                      alertLatencyMs=payload.get("alertLatencyMs"))
                return original_on_threat(payload, *callback_args, **callback_kwargs)
            self.on_threat_fn = on_threat
    pipeline_render.RenderThread.__init__ = render_init

    original_observe = pipeline_render.RenderThread._observe
    def observe(self, snap, now):
        result = original_observe(self, snap, now)
        if result.get("confirmed_alert") and result.get("decision_sample_accepted"):
            decision_at = time.perf_counter()
            sequence = snap.get("inference_sequence")
            context = {
                "decision_at": decision_at,
                "capture_timestamp": snap.get("capture_timestamp"),
                "inference_sequence": sequence,
            }
            self._bench_decision_contexts[sequence] = context
            event("decision", at=decision_at, **context)
        return result
    pipeline_render.RenderThread._observe = observe

    original_emit_alert = pipeline_render.RenderThread._emit_alert
    def emit_alert(self, snap, decision, annotated):
        sequence = snap.get("inference_sequence")
        self._bench_alert_context = self._bench_decision_contexts.pop(sequence, None)
        try:
            return original_emit_alert(self, snap, decision, annotated)
        finally:
            self._bench_alert_context = None
    pipeline_render.RenderThread._emit_alert = emit_alert
    timed(pipeline_render.RenderThread, "_render_frame", "render")
    original_frame = api.state.set_frame
    def set_frame(camera_id, jpg):
        original_frame(camera_id, jpg)
        event("display", bytes=len(jpg))
    api.state.set_frame = set_frame
    original_meta = api.state.set_detection_meta
    def set_meta(camera_id, meta):
        original_meta(camera_id, meta)
        event("metadata", score=meta.get("threat_confidence"), weapon_score=meta.get("weapon_score"),
              inference_frame=meta.get("frame_idx"), multi_threat=meta.get("multiThreat"))
    api.state.set_detection_meta = set_meta
    original_alert = api.state.register_alert
    def register_alert(payload):
        original_alert(payload)
        event("alert", alert_id=payload.get("id"), score=payload.get("confidence"))
    api.state.register_alert = register_alert
    original_sse_generator = api._sse_generator
    async def sse_generator(channel):
        async for chunk in original_sse_generator(channel):
            if chunk.startswith(b"data: "):
                try:
                    payload = json.loads(chunk[6:].strip())
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = None
                if isinstance(payload, dict) and payload.get("id"):
                    event("sse_emitted", alert_id=payload.get("id"),
                          alertLatencyMs=payload.get("alertLatencyMs"))
            yield chunk
    api._sse_generator = sse_generator
    original_encode = api.cv2.imencode
    def encode(*args, **kwargs):
        start = time.perf_counter()
        result = original_encode(*args, **kwargs)
        event("jpeg_encode", start, ok=result[0])
        return result
    api.cv2.imencode = encode
    original_queue = mp.Queue
    def make_queue(maxsize=0, *args, **kwargs):
        instance = original_queue(maxsize, *args, **kwargs)
        return FrameQueueProbe(instance) if maxsize == 3 else instance
    mp.Queue = make_queue
    inference_process.inference_worker = instrumented_worker
    return api


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", required=True, help="Local video path or camera index")
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--seconds", type=float, default=90)
    parser.add_argument("--all-detection", action="store_true")
    args = parser.parse_args()
    if args.seconds <= 0 or args.seconds > 7200:
        parser.error("seconds must be between 0 and 7200")
    source = int(args.source) if args.source.isdigit() else str(Path(args.source).resolve(strict=True))
    api = configure(args.output.resolve(), source, args.all_detection)
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(api.app, host="127.0.0.1", port=args.port, log_level="warning", timeout_graceful_shutdown=5))

    def stop_after_ready_window():
        while not server.started and not server.should_exit:
            time.sleep(0.05)
        if not server.started:
            return
        startup_deadline = time.monotonic() + args.seconds + 120
        while not server.should_exit and time.monotonic() < startup_deadline:
            if benchmark_models_ready(args.output.resolve(), args.all_detection):
                break
            time.sleep(0.5)
        ready = benchmark_models_ready(args.output.resolve(), args.all_detection)
        benchmark_started = time.perf_counter()
        write_json(args.output.resolve() / "benchmark-start.json", {
            "ready": ready,
            "started_monotonic": benchmark_started,
            "required_models": ["violence", "weapon"] if args.all_detection else ["violence"],
        })
        if not ready:
            server.should_exit = True
            return
        deadline = time.monotonic() + args.seconds
        while not server.should_exit and time.monotonic() < deadline:
            time.sleep(0.05)
        server.should_exit = True

    timer = threading.Thread(target=stop_after_ready_window, name="bench-runtime-timer", daemon=True)
    timer.start()
    try:
        server.run()
    finally:
        timer.join(timeout=1)
        flush()


if __name__ == "__main__":
    mp.freeze_support()
    main()
