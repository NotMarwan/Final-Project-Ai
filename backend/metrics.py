"""Real-time performance metrics and end-to-end pipeline telemetry.

Owned by slice S-08 (workstream WT-13). Historical surface (``PipelineMetrics``,
``record_capture``/``record_inference``/``record_encode``/``record_stream``/
``record_weapon``/``record_person``/``summary`` and the module singleton
``pipeline_metrics``) is preserved unchanged and extended additively.

Design rules encoded here (see ``docs/campaign/engineering/13-telemetry-audit.md``):

* Every timestamp field carries its clock domain and unit in the name
  (``...AtMonoMs`` = ``time.monotonic()*1000``, ``...AtEpochMs`` = ``time.time()*1000``);
  every duration carries the ``Ms`` suffix and is a single-clock difference.
* An unmeasured quantity is ``None`` / an absent key with an explicit reason, never ``0``.
* Counters are cumulative and monotone per ``processRunId``; a regression without a new
  ``processRunId`` is reported as a fault (``counterRegressionDetected``), never smoothed.
* No silent failure paths: every swallowed error is recorded in ``faults`` and/or the
  ``subsystems`` health registry, both of which are exported.

The machine-readable contract consumed by ``bench/`` and the UI is
``export_snapshot()`` (schema ``sentinel-metrics-export/1``), exposed through
``GET /system/metrics`` (``summary()["metricsExport"]``) and ``GET /system/status``
(``metrics`` + ``subsystems``). Ingest is driven by the additive api.py hunks on
``/detections`` and ``/system/status``; producers may also call the ``record_*``
hooks in-process.
"""
from __future__ import annotations

import math
import os
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, Iterable, List, Optional, Tuple

SCHEMA_VERSION = "sentinel-metrics-export/1"
WINDOW_MAXLEN = 600
RATE_WINDOW_MAXLEN = 900
RECENT_FAULTS_MAXLEN = 64

# ── Clock domains (SC-6). Reference only — never used to cross-subtract. ──────
# Measured on the project venv interpreter (CPython 3.12.5, Windows): time.monotonic()
# and time.time() quantize to 15.625 ms (GetTickCount64 / GetSystemTimeAsFileTime), while
# time.perf_counter() is QueryPerformanceCounter (~0.2 µs). Durations must use perf_counter.
_MONOTONIC_QUANTIZATION_MS = time.get_clock_info("monotonic").resolution * 1000.0

CLOCK_DOMAINS: Dict[str, str] = {
    "capture-monotonic": "time.monotonic()*1000 at frame read in the capture loop (producer thread)",
    "worker-monotonic": "time.monotonic()*1000 inside the spawned inference worker process",
    "api-monotonic": "time.monotonic()*1000 inside the FastAPI process",
    "perf-counter": "time.perf_counter()*1000 (QueryPerformanceCounter); the only sub-millisecond clock available here",
    "qpc-perf-counter": "producer-declared captureClockBase=\"perf-qpc\": cross-boundary ages are computed on the perf_counter base only",
    "monotonic-gettickcount64": "producer-declared captureClockBase=\"monotonic-gettickcount64\": cross-boundary ages are computed on time.monotonic() and inherit its 15.625 ms quantization",
    "wall-epoch": "time.time()*1000 (UTC wall clock)",
    "ui-epoch": "Date.now() in the browser",
    "media": "source media clock (file PTS-derived sample_timestamp); unrelated to monotonic/wall clocks",
    "decision-sample-clock": ("decision layer sample clock (sample_time/current_time domain used by "
                              "LiveAlertDecisionLayer.update); exact string published per measurement in "
                              "decision.confirmLatencyClock"),
}

_CLOCK_QUANTIZATION = {
    "monotonicResolutionMs": _MONOTONIC_QUANTIZATION_MS,
    "wallEpochResolutionMs": time.get_clock_info("time").resolution * 1000.0,
    "perfCounterResolutionMs": time.get_clock_info("perf_counter").resolution * 1000.0,
    "monotonicImplementation": time.get_clock_info("monotonic").implementation,
    "perfCounterImplementation": time.get_clock_info("perf_counter").implementation,
    "note": ("sub-tick durations measured on the monotonic/wall base collapse to 0 or multiples of the "
             "resolution; every duration and every rate-window delta in this export uses time.perf_counter"),
}

EXPORT_RULES: List[str] = [
    "Durations are single-clock differences only; never subtract across clock domains.",
    "time.monotonic() is machine-wide: same-machine monotonic differences are comparable,"
    " but they are still labelled with their producing domain.",
    "On CPython 3.12/Windows time.monotonic() and time.time() are 15.625 ms quantized"
    " (GetTickCount64/GetSystemTimeAsFileTime); use time.perf_counter for durations.",
    "Processing latency (capture->result build) is NOT glass-to-alert; glass-to-alert"
    " requires independent onset labelling and is unavailable here.",
    "Capture rate, render rate, publication rate and per-model completed-inference rate are"
    " reported separately and never combined into one number.",
    "A null / missing distribution means unmeasured (n==0); it is never zero.",
    "Cumulative counters are monotone per (processRunId); a regression without a new"
    " processRunId is a fault, not a data point.",
    "Rates always carry numerator + denominator + window + sample count + processRunId.",
]


def _mono_ms() -> float:
    """Wall-independent monotonic stamp used ONLY to subtract producer monotonic stamps."""
    return time.monotonic() * 1000.0


def _perf_ms() -> float:
    """QueryPerformanceCounter stamp used for every rate window and queue delta."""
    return time.perf_counter() * 1000.0

FIELD_NAMING: Dict[str, str] = {
    "absoluteTimestamp": "<name>AtMonoMs | <name>AtEpochMs (unit + clock domain in the name)",
    "duration": "<name>Ms (single-clock difference)",
    "counter": "<name>Count | <name>Dropped | <name>Total (cumulative, monotone per run)",
    "rate": "<name>Fps | <name>PerSec (with numerator/denominator/window)",
    "distribution": "{p05, median, p95, min, max, n, unit, clockDomain[, synced]}",
}

# Canonical camelCase field names accepted from producers on the result-dict snapshot.
# snake_case aliases are accepted so producers can land instrumentation incrementally.
_COUNTER_ALIASES: Dict[str, Tuple[str, ...]] = {
    "personCompletedCount": ("personCompletedCount", "person_completed_count"),
    "violenceCompletedCount": ("violenceCompletedCount", "violence_completed_count"),
    "weaponCompletedCount": ("weaponCompletedCount", "weapon_completed_count"),
    "framesReadCount": ("framesReadCount", "frames_read"),
    "duplicateFrameCount": ("duplicateFrameCount", "duplicateFrames", "duplicate_frame_count"),
    "reconnectCount": ("reconnectCount", "reconnects", "reconnect_count"),
}

_STAGE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "frameRead": ("stageFrameReadMs", "stage_frame_read_ms"),
    "captureToQueue": ("stageCaptureToQueueMs", "stage_capture_to_queue_ms"),
    "preprocess": ("stagePreprocessMs", "stage_preprocess_ms"),
    "serialize": ("stageSerializeMs", "stage_serialize_ms"),
    "enqueueToDequeue": ("stageEnqueueToDequeueMs", "stage_ipc_transfer_ms", "stage_enqueue_to_dequeue_ms"),
    "inferenceWait": ("stageInferenceWaitMs", "stage_inference_wait_ms"),
    "inferenceCompute": ("stageInferenceComputeMs", "stage_inference_compute_ms"),
    "modelLoad": ("stageModelLoadMs", "startupModelLoadMs", "stage_model_load_ms"),
    "firstInference": ("stageFirstInferenceMs", "startupFirstFrameMs", "stage_first_inference_ms"),
    "engineBuild": ("stageEngineBuildMs", "stage_engine_build_ms"),
    "inferenceColdStart": ("inferenceColdStartMs", "inference_cold_start_ms"),
}

_STAGE_CLOCK_DOMAIN: Dict[str, str] = {
    "frameRead": "capture-monotonic",
    "captureToQueue": "capture-monotonic",
    "preprocess": "worker-monotonic",
    "serialize": "worker-monotonic",
    "enqueueToDequeue": "worker-monotonic",
    "inferenceWait": "worker-monotonic",
    "inferenceCompute": "worker-monotonic",
    "modelLoad": "worker-monotonic",
    "firstInference": "worker-monotonic",
    "engineBuild": "worker-monotonic",
    "inferenceColdStart": "worker-monotonic",
}

_QUEUE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "frameDepth": ("frameQueueDepth", "frame_queue_depth"),
    "frameDroppedTotal": ("frameQueueDropped", "frame_queue_dropped"),
    "frameDroppedDerivedTotal": ("frameQueueDroppedDerived", "frame_queue_dropped_derived"),
    "resultDepth": ("resultQueueDepth", "result_queue_depth"),
    "resultDroppedTotal": ("resultQueueDropped", "result_queue_dropped"),
    "backlogFrames": ("backlogFrames", "backlog_frames"),
}

# public protocol names emitted on the /detections `pipeline` block (agreed with WT-14/WT-15)
_QUEUE_PUBLIC_NAMES: Dict[str, str] = {
    "frameDepth": "frameDepth",
    "frameDroppedTotal": "frameQueueDropped",
    "frameDroppedDerivedTotal": "frameQueueDroppedDerived",
    "resultDepth": "resultDepth",
    "resultDroppedTotal": "resultQueueDropped",
    "backlogFrames": "backlogFrames",
}


def _finite(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _non_negative(value: object) -> Optional[float]:
    number = _finite(value)
    return number if number is not None and number >= 0 else None


def _first_present(mapping: Dict[str, object], names: Iterable[str]) -> object:
    for name in names:
        if name in mapping:
            value = mapping[name]
            if value is not None:
                return value
    return None


def _percentile(ordered: List[float], q: float) -> Optional[float]:
    if not ordered:
        return None
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[low])
    return float(ordered[low] + (ordered[high] - ordered[low]) * (position - low))


def _distribution(values: Iterable[float], unit: str, clock_domain: Optional[str] = None,
                  synced: Optional[bool] = None) -> Optional[dict]:
    numbers = [float(v) for v in values]
    if not numbers:
        return None
    ordered = sorted(numbers)
    payload = {
        "p05": round(_percentile(ordered, 0.05), 3),
        "median": round(_percentile(ordered, 0.50), 3),
        "p95": round(_percentile(ordered, 0.95), 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
        "n": len(ordered),
        "unit": unit,
    }
    if clock_domain is not None:
        payload["clockDomain"] = clock_domain
    if synced is not None:
        payload["synced"] = bool(synced)
    return payload


def _rate(samples: Deque[Tuple[float, ...]], *, source: str,
          counter: bool = False) -> Optional[dict]:
    if len(samples) < 2:
        return None
    if counter:
        # counters are monotone per processRunId: only the trailing run segment is a
        # valid rate window; a run boundary must never be treated as a counter delta.
        trailing_run = samples[-1][2] if len(samples[-1]) > 2 else None
        segment = [sample for sample in samples
                   if (sample[2] if len(sample) > 2 else None) == trailing_run]
        if len(segment) < 2:
            return None
        first, last = segment[0], segment[-1]
        window_ms = last[0] - first[0]
        if window_ms <= 0:
            return None
        window_seconds = window_ms / 1000.0
        delta = last[1] - first[1]
        if delta < 0:
            return None
        return {
            "perSec": round(delta / window_seconds, 4),
            "numerator": round(delta, 3),
            "denominatorSeconds": round(window_seconds, 3),
            "windowSeconds": round(window_seconds, 3),
            "samples": len(segment),
            "processRunId": trailing_run,
            "stationary": delta == 0,
            "clockDomain": "perf-counter",
            "source": source,
        }
    first, last = samples[0], samples[-1]
    window_ms = last[0] - first[0]
    if window_ms <= 0:
        return None
    window_seconds = window_ms / 1000.0
    values = [sample[1] for sample in samples]
    return {
        "perSec": round(sum(values) / len(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "numerator": round(sum(values), 3),
        "denominatorSeconds": round(window_seconds, 3),
        "windowSeconds": round(window_seconds, 3),
        "samples": len(values),
        "clockDomain": "perf-counter",
        "source": source,
    }


@dataclass
class PipelineMetrics:
    # ── legacy surface (names and semantics frozen) ──────────────────────────
    capture_fps: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    inference_latency_ms: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    encode_latency_ms: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    stream_fps: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    weapon_score: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    person_count: Deque[int] = field(default_factory=lambda: deque(maxlen=60))

    # ── telemetry state (additive) ───────────────────────────────────────────
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)
    _stage_windows: Dict[str, Deque[float]] = field(default_factory=dict, repr=False)
    _stage_models: Dict[str, Optional[str]] = field(default_factory=dict, repr=False)
    _stage_sync: Dict[str, Optional[bool]] = field(default_factory=dict, repr=False)
    _stage_clock: Dict[str, str] = field(default_factory=dict, repr=False)
    _stage_cuda_sync: Dict[str, bool] = field(default_factory=dict, repr=False)
    _reported_rates: Dict[str, Deque[Tuple[float, float]]] = field(default_factory=dict, repr=False)
    _counter_windows: Dict[str, Deque[Tuple[float, float]]] = field(default_factory=dict, repr=False)
    _counters: Dict[str, dict] = field(default_factory=dict, repr=False)
    _queues: Dict[str, dict] = field(default_factory=dict, repr=False)
    _capture_health: Dict[str, object] = field(default_factory=dict, repr=False)
    _faults: Dict[str, int] = field(default_factory=dict, repr=False)
    _fault_log: Deque[dict] = field(default_factory=lambda: deque(maxlen=RECENT_FAULTS_MAXLEN), repr=False)
    _subsystems: Dict[str, dict] = field(default_factory=dict, repr=False)
    _observation: dict = field(default_factory=dict, repr=False)
    _decision: dict = field(default_factory=dict, repr=False)
    _resources: dict = field(default_factory=dict, repr=False)
    _run_provenance: dict = field(default_factory=dict, repr=False)
    _sequence_by_camera: Dict[str, float] = field(default_factory=dict, repr=False)
    _run_by_camera: Dict[str, str] = field(default_factory=dict, repr=False)
    _publication_run_counts: Dict[str, float] = field(default_factory=dict, repr=False)
    _last_resource_sample_perf_ms: Optional[float] = field(default=None, repr=False)
    _resource_ttl_ms: float = field(default=2000.0, repr=False)
    _last_ingest_mono_ms: Optional[float] = field(default=None, repr=False)
    _last_ingest_perf_ms: Optional[float] = field(default=None, repr=False)

    # ── legacy recorder methods (unchanged behaviour) ────────────────────────
    def record_capture(self, fps: float):
        self.capture_fps.append(fps)
        self.record_reported_rate("captureFps", fps)

    def record_inference(self, latency_ms: float):
        self.inference_latency_ms.append(latency_ms)
        self.record_stage("inferenceLatency", latency_ms, clock_domain="worker-monotonic")

    def record_encode(self, latency_ms: float):
        self.encode_latency_ms.append(latency_ms)
        self.record_stage("encode", latency_ms, clock_domain="api-monotonic")

    def record_stream(self, fps: float):
        self.stream_fps.append(fps)
        self.record_reported_rate("renderFps", fps)

    def record_weapon(self, score: float):
        self.weapon_score.append(score)

    def record_person(self, count: int):
        self.person_count.append(count)

    # ── additive recorder API ────────────────────────────────────────────────
    def record_stage(self, stage: str, ms: object, *, model: Optional[str] = None,
                     synced: Optional[bool] = None, cuda_sync: Optional[bool] = None,
                     clock_domain: Optional[str] = None) -> None:
        value = _non_negative(ms)
        if value is None:
            self._record_fault("stageSampleRejected", f"stage {stage} received non-measured value {ms!r}")
            return
        key = f"{model}:{stage}" if model else stage
        with self._lock:
            self._stage_windows.setdefault(key, deque(maxlen=WINDOW_MAXLEN)).append(value)
            self._stage_models[key] = model
            if synced is not None:
                self._stage_sync[key] = bool(synced)
            if cuda_sync is not None:
                self._stage_cuda_sync[key] = bool(cuda_sync)
            if clock_domain is None:
                clock_domain = _STAGE_CLOCK_DOMAIN.get(stage, "unspecified")
            self._stage_clock[key] = clock_domain

    def record_reported_rate(self, name: str, value: object, *, at_ms: Optional[float] = None) -> None:
        number = _non_negative(value)
        if number is None:
            self._record_fault("rateSampleRejected", f"rate {name} received non-measured value {value!r}")
            return
        stamp = at_ms if isinstance(at_ms, (int, float)) else _perf_ms()
        with self._lock:
            self._reported_rates.setdefault(name, deque(maxlen=RATE_WINDOW_MAXLEN)).append((float(stamp), number))

    def observe_counter(self, name: str, value: object, *, run_id: Optional[str] = None,
                        producer: Optional[str] = None, at_ms: Optional[float] = None) -> None:
        number = _non_negative(value)
        if number is None:
            self._record_fault("counterSampleRejected", f"counter {name} received non-measured value {value!r}")
            return
        stamp = at_ms if isinstance(at_ms, (int, float)) else _perf_ms()
        with self._lock:
            previous = self._counters.get(name)
            if previous is not None:
                previous_run = previous.get("runId")
                if run_id is not None and previous_run is not None and previous_run != run_id:
                    # new process run: counters restart legitimately; history stays for
                    # trend, but rate windows never cross a run boundary (see _rate).
                    pass
                elif number < float(previous.get("value", 0.0)):
                    self._record_fault(
                        "counterRegressionDetected",
                        f"counter {name} regressed {previous.get('value')} -> {number} without a new processRunId",
                    )
                    self._counter_windows.pop(name, None)
            effective_run = run_id if run_id is not None else (previous.get("runId") if previous else None)
            self._counters[name] = {
                "value": number,
                "unit": "count",
                "runId": effective_run,
                "producer": producer if producer is not None else (previous.get("producer") if previous else None),
                "lastAtPerfMs": round(float(stamp), 1),
            }
            self._counter_windows.setdefault(name, deque(maxlen=RATE_WINDOW_MAXLEN)).append(
                (float(stamp), number, effective_run))

    def record_queue(self, name: str, *, depth: object = None, dropped_total: object = None,
                     derived_dropped_total: object = None, producer: Optional[str] = None) -> None:
        with self._lock:
            entry = self._queues.setdefault(name, {
                "depthNow": None, "depthSamples": deque(maxlen=WINDOW_MAXLEN),
                "droppedTotal": None, "derivedDroppedTotal": None, "producer": producer,
                "lastAtPerfMs": None,
            })
            depth_value = _non_negative(depth)
            if depth_value is not None:
                entry["depthNow"] = int(depth_value)
                entry["depthSamples"].append(float(depth_value))
            dropped_value = _non_negative(dropped_total)
            if dropped_value is not None:
                entry["droppedTotal"] = int(dropped_value)
                if entry.get("droppedBaselineAtPerfMs") is None:
                    entry["droppedBaselineAtPerfMs"] = _perf_ms()
                    entry["droppedBaselineValue"] = int(dropped_value)
            derived_value = _non_negative(derived_dropped_total)
            if derived_value is not None:
                entry["derivedDroppedTotal"] = int(derived_value)
            if producer is not None:
                entry["producer"] = producer
            entry["lastAtPerfMs"] = round(_perf_ms(), 1)

    def record_capture_health(self, health: dict) -> None:
        with self._lock:
            for key in ("negotiatedWidth", "negotiatedHeight", "negotiatedFps", "negotiatedFourcc",
                        "requestedWidth", "requestedHeight", "requestedFps", "requestedFourcc"):
                if key in health and health[key] is not None:
                    self._capture_health[key] = health[key]
            for key in ("readGapP50Ms", "readGapP95Ms", "readGapMaxMs", "readGapSampleCount"):
                if key in health and _non_negative(health[key]) is not None:
                    self._capture_health[key] = health[key]

    def record_decision_event(self, kind: Optional[str], *, mono_ms: Optional[float] = None,
                              confirm_latency_ms: Optional[float] = None,
                              confirm_latency_clock: Optional[str] = None) -> None:
        """Record a decision state transition and/or a confirm-latency measurement.

        ``kind=None`` means "no state was observed in this snapshot": only the latency is
        recorded and the state machine is left untouched (never inferred).
        """
        stamp = mono_ms if isinstance(mono_ms, (int, float)) else _mono_ms()
        with self._lock:
            if kind is not None:
                state = str(kind)
                previous = self._decision.get("state")
                if previous != state:
                    if previous is not None:
                        self._decision.setdefault("transitions", deque(maxlen=RECENT_FAULTS_MAXLEN)).append({
                            "from": previous, "to": state, "atMonoMs": round(float(stamp), 1),
                        })
                        if previous not in ("NORMAL",) and self._decision.get("stateSinceMonoMs") is not None:
                            duration = float(stamp) - float(self._decision["stateSinceMonoMs"])
                            self.record_stage("decisionStateDuration", duration, clock_domain="api-monotonic")
                    self._decision["state"] = state
                    self._decision["stateSinceMonoMs"] = round(float(stamp), 1)
            latency = _non_negative(confirm_latency_ms)
            if latency is not None:
                self._decision.setdefault("confirmLatencySamples", deque(maxlen=WINDOW_MAXLEN)).append(latency)
            if confirm_latency_clock:
                self._decision["confirmLatencyClock"] = confirm_latency_clock

    def set_subsystem_health(self, name: str, status: str, reason: str = "",
                             detail: Optional[dict] = None) -> None:
        with self._lock:
            self._subsystems[name] = {
                "status": str(status).upper(),
                "reason": str(reason)[:300],
                "detail": detail,
                "updatedAtEpochMs": round(time.time() * 1000.0, 1),
            }

    def set_run_provenance(self, **fields) -> None:
        with self._lock:
            for key, value in fields.items():
                if value is not None:
                    self._run_provenance[key] = value

    # ── ingest ───────────────────────────────────────────────────────────────
    def observe_detection_snapshot(self, snapshot: object, *, camera_id: Optional[str] = None) -> dict:
        """Ingest one detection snapshot (raw result dict or built payload).

        Never raises: malformed input is counted as a fault and surfaced in health.
        """
        if not isinstance(snapshot, dict):
            self._record_fault("snapshotMalformed", f"snapshot is {type(snapshot).__name__}, not a mapping")
            return {"ingested": False, "reason": "malformed snapshot"}
        now_mono_ms = _mono_ms()
        try:
            return self._ingest(dict(snapshot), camera_id, now_mono_ms)
        except Exception as exc:  # surfaced, never silent
            self._record_fault("ingestFailed", f"{type(exc).__name__}: {exc}")
            return {"ingested": False, "reason": f"{type(exc).__name__}: {exc}"}

    def _ingest(self, snap: dict, camera_id: Optional[str], now_mono_ms: float) -> dict:
        now_perf_ms = _perf_ms()
        run_id = snap.get("processRunId") or snap.get("process_run_id")
        run_id = str(run_id) if run_id not in (None, "") else None
        producer = snap.get("workerPid") or snap.get("worker_pid")
        producer = f"worker-pid:{producer}" if producer not in (None, "") else None
        generation = _non_negative(snap.get("inferenceGeneration") or snap.get("inference_generation"))

        with self._lock:
            self._last_ingest_mono_ms = now_mono_ms
            self._last_ingest_perf_ms = now_perf_ms
            observation = self._observation
            observation["ingestCount"] = int(observation.get("ingestCount", 0)) + 1
            observation.setdefault("firstObservedAtMonoMs", round(now_mono_ms, 1))
            observation["lastObservedAtMonoMs"] = round(now_mono_ms, 1)
            observation["lastObservedAtPerfMs"] = round(now_perf_ms, 1)
            if camera_id:
                cameras = observation.setdefault("cameraIds", [])
                if camera_id not in cameras:
                    cameras.append(camera_id)

        # cumulative counters (SC-7)
        for canonical, aliases in _COUNTER_ALIASES.items():
            raw = _first_present(snap, aliases)
            if raw is not None:
                self.observe_counter(canonical, raw, run_id=run_id, producer=producer, at_ms=now_perf_ms)

        # publication counter: one per distinct inference_sequence per camera
        sequence = _non_negative(_first_present(snap, ("inferenceSequence", "inference_sequence")))
        if sequence is not None:
            key = camera_id or "unknown"
            with self._lock:
                previous = self._sequence_by_camera.get(key)
                previous_run = self._run_by_camera.get(key)
                restarted = previous_run is not None and run_id is not None and previous_run != run_id
                if previous is not None and sequence < previous and not restarted:
                    self._record_fault(
                        "nonMonotoneSequenceDetected",
                        f"camera {key}: inference sequence {previous} -> {sequence} without a new processRunId",
                    )
                if previous is None or sequence > previous or restarted:
                    self._sequence_by_camera[key] = sequence
                    self._observation["distinctSequenceCount"] = int(self._observation.get("distinctSequenceCount", 0)) + 1
                if run_id is not None:
                    self._run_by_camera[key] = run_id
            self._bump_publication_counter(now_perf_ms, run_id, producer)

        # explicitly-named producer rates. The result-dict `fps` field is deliberately NOT
        # ingested: runtime-map §1.3 records it as always 0.0 from default_result().
        for rate_name, aliases in (("captureFps", ("captureFps", "capture_fps")),
                                   ("renderFps", ("renderFps", "render_fps"))):
            raw_rate = _non_negative(_first_present(snap, aliases))
            if raw_rate is not None:
                self.record_reported_rate(rate_name, raw_rate, at_ms=now_perf_ms)

        # stage timings
        for canonical, aliases in _STAGE_ALIASES.items():
            raw = _first_present(snap, aliases)
            if raw is not None:
                self.record_stage(canonical, raw)
        nested = snap.get("inferenceTimings") or snap.get("inference_timings")
        if isinstance(nested, list):
            for item in nested:
                if not isinstance(item, dict):
                    continue
                model = item.get("model")
                synced = item.get("inferenceComputeSynced")
                for stage_key in ("stageInferenceComputeMs", "stageInferenceWaitMs", "stagePreprocessMs"):
                    raw = item.get(stage_key)
                    if raw is None:
                        continue
                    canonical = {
                        "stageInferenceComputeMs": "inferenceCompute",
                        "stageInferenceWaitMs": "inferenceWait",
                        "stagePreprocessMs": "preprocess",
                    }[stage_key]
                    self.record_stage(canonical, raw, model=str(model) if model else None,
                                      synced=bool(synced) if isinstance(synced, bool) else None,
                                      cuda_sync=item.get("cudaSyncApplied") if isinstance(item.get("cudaSyncApplied"), bool) else None)
        synced_flag = snap.get("inferenceComputeSynced")
        if isinstance(synced_flag, bool):
            self._stage_sync["inferenceCompute"] = synced_flag
        cuda_flag = snap.get("cudaSyncApplied")
        if isinstance(cuda_flag, bool):
            self._stage_cuda_sync["inferenceCompute"] = cuda_flag

        # frame age
        frame_age = _non_negative(_first_present(snap, ("frameAgeMs", "frame_age_ms")))
        capture_clock_base = snap.get("captureClockBase") or snap.get("capture_clock_base")
        capture_clock_base = capture_clock_base if isinstance(capture_clock_base, str) and capture_clock_base else None
        if capture_clock_base is not None:
            self._observation["captureClockBase"] = capture_clock_base
        if frame_age is not None:
            self.record_stage("frameAgeAtInferenceStart", frame_age,
                              clock_domain=capture_clock_base or "capture-monotonic")
        clock_source = snap.get("frameAgeClockSource") or snap.get("frame_age_clock_source")
        explicit_publication_age = _non_negative(
            _first_present(snap, ("frameAgeAtPublicationMs", "frame_age_at_publication_ms")))
        published_age = self._frame_age_at_publication(snap, now_mono_ms, now_perf_ms)
        if published_age is not None:
            if explicit_publication_age is not None:
                publication_domain = "producer-supplied"
            else:
                publication_domain = "qpc-same-machine" if capture_clock_base == "perf-qpc" else "monotonic-same-machine"
            self.record_stage("frameAgeAtPublication", published_age, clock_domain=publication_domain)
        with self._lock:
            if isinstance(clock_source, str) and clock_source:
                self._observation["frameAgeClockSource"] = clock_source
            media_clock = snap.get("source_sample_timestamp", snap.get("sourceSampleTimestamp"))
            if isinstance(media_clock, (int, float)) and math.isfinite(float(media_clock)):
                self._observation["mediaClockLastValue"] = float(media_clock)
                self._observation["mediaClockDomain"] = "media"
            wall = _first_present(snap, ("updatedAt", "updated_at", "timestamp"))
            wall_number = _finite(wall)
            if wall_number is not None and wall_number > 0:
                observation["lastUpdatedAtEpochMs"] = round(wall_number * 1000.0, 1) if wall_number < 1e11 else round(wall_number, 1)

        # queues
        with self._lock:
            frame_depth = _non_negative(_first_present(snap, _QUEUE_ALIASES["frameDepth"]))
            frame_dropped = _non_negative(_first_present(snap, _QUEUE_ALIASES["frameDroppedTotal"]))
            frame_derived = _non_negative(_first_present(snap, _QUEUE_ALIASES["frameDroppedDerivedTotal"]))
            result_depth = _non_negative(_first_present(snap, _QUEUE_ALIASES["resultDepth"]))
            result_dropped = _non_negative(_first_present(snap, _QUEUE_ALIASES["resultDroppedTotal"]))
        if any(value is not None for value in (frame_depth, frame_dropped, frame_derived)):
            self.record_queue("frame", depth=frame_depth, dropped_total=frame_dropped,
                              derived_dropped_total=frame_derived, producer=producer)
        if any(value is not None for value in (result_depth, result_dropped)):
            self.record_queue("result", depth=result_depth, dropped_total=result_dropped, producer=producer)
        backlog = _non_negative(_first_present(snap, _QUEUE_ALIASES["backlogFrames"]))
        if backlog is not None:
            self.record_stage("backlogFrames", backlog, clock_domain="worker-monotonic")

        # capture negotiation health (WT-14)
        capture_health = snap.get("captureHealth") or snap.get("capture_health")
        if isinstance(capture_health, dict):
            self.record_capture_health(capture_health)

        # decision state transitions (observed, not glass-to-alert). WT-20 publishes the
        # confirm latency on the alert payload (camelCase) and inside the decision response
        # (`decision_layer`, snake_case) — accept both containers without renaming anything.
        decision = snap.get("decision") if isinstance(snap.get("decision"), dict) else {}
        decision_layer = snap.get("decision_layer") if isinstance(snap.get("decision_layer"), dict) else {}
        alert_state = (snap.get("alert_state") or snap.get("alertState")
                       or decision.get("alertState") or decision.get("alert_state")
                       or decision_layer.get("alert_state") or decision_layer.get("alertState"))
        confirm_latency = None
        confirm_clock = None
        for container in (snap, decision_layer, decision):
            if confirm_latency is None:
                confirm_latency = _non_negative(
                    _first_present(container, ("decisionConfirmLatencyMs", "decision_confirm_latency_ms")))
            if confirm_clock is None:
                raw_clock = _first_present(
                    container, ("decisionConfirmLatencyClock", "decision_confirm_latency_clock"))
                if isinstance(raw_clock, str) and raw_clock:
                    confirm_clock = raw_clock[:200]
        if isinstance(alert_state, str) and alert_state:
            normalized = "CONFIRMED" if alert_state == "CONFIRMED_VIOLENCE" else alert_state
            self.record_decision_event(normalized, mono_ms=now_mono_ms, confirm_latency_ms=confirm_latency,
                                       confirm_latency_clock=confirm_clock)
        elif confirm_latency is not None:
            # latency without a state in this snapshot: record the measurement, never a state
            self.record_decision_event(None, mono_ms=now_mono_ms, confirm_latency_ms=confirm_latency,
                                       confirm_latency_clock=confirm_clock)

        return {"ingested": True, "runId": run_id, "atMonoMs": round(now_mono_ms, 1)}

    def _bump_publication_counter(self, now_perf_ms: float, run_id: Optional[str], producer: Optional[str]) -> None:
        with self._lock:
            key = run_id or "unknown"
            value = self._publication_run_counts.get(key, 0.0) + 1.0
            self._publication_run_counts[key] = value
            self._counters["publicationCount"] = {
                "value": value, "unit": "count", "runId": run_id,
                "producer": producer or "telemetry-ingest", "lastAtPerfMs": round(now_perf_ms, 1),
            }
            self._counter_windows.setdefault("publicationCount", deque(maxlen=RATE_WINDOW_MAXLEN)).append(
                (now_perf_ms, value, key))

    def _frame_age_at_publication(self, snap: dict, now_mono_ms: float,
                                  now_perf_ms: Optional[float] = None) -> Optional[float]:
        explicit = _non_negative(_first_present(snap, ("frameAgeAtPublicationMs", "frame_age_at_publication_ms")))
        if explicit is not None:
            return explicit
        # Derive only on the declared capture base: subtracting a QPC-based producer stamp
        # from a GetTickCount64 stamp (or vice versa) would be a cross-base subtraction.
        base = snap.get("captureClockBase") or snap.get("capture_clock_base")
        now = now_perf_ms if (base == "perf-qpc" and now_perf_ms is not None) else now_mono_ms
        captured_mono_ms = _non_negative(_first_present(snap, ("capturedAtMonoMs", "captured_at_mono_ms")))
        if captured_mono_ms is not None:
            age = now - captured_mono_ms
            return age if age >= 0 else None
        captured_seconds = _non_negative(_first_present(snap, ("capture_timestamp", "violence_capture_timestamp")))
        if captured_seconds is not None and captured_seconds > 0:
            age = (now / 1000.0 - captured_seconds) * 1000.0
            return age if age >= 0 else None
        return None

    # ── per-frame payload for /detections ────────────────────────────────────
    def detection_telemetry_payload(self, snapshot: object, camera_id: Optional[str] = None) -> dict:
        """Compact per-frame telemetry block attached additively to the /detections payload."""
        snap = snapshot if isinstance(snapshot, dict) else {}
        unavailable: List[str] = []
        boolean = snap.get("inferenceComputeSynced")
        stages: Dict[str, Optional[float]] = {}
        for name, aliases in _STAGE_ALIASES.items():
            value = _non_negative(_first_present(snap, aliases))
            stages[name] = round(value, 3) if value is not None else None
            if value is None and name in ("frameRead", "captureToQueue", "preprocess", "enqueueToDequeue",
                                          "inferenceWait", "inferenceCompute"):
                unavailable.append(f"stageMs.{name}")
        queues: Dict[str, Optional[float]] = {}
        for name, aliases in _QUEUE_ALIASES.items():
            value = _non_negative(_first_present(snap, aliases))
            public_name = _QUEUE_PUBLIC_NAMES[name]
            queues[public_name] = int(value) if value is not None else None
            if value is None:
                unavailable.append(f"queues.{public_name}")
        counters: Dict[str, Optional[float]] = {}
        for canonical, aliases in _COUNTER_ALIASES.items():
            value = _non_negative(_first_present(snap, aliases))
            counters[canonical] = int(value) if value is not None else None
        frame_age = _non_negative(_first_present(snap, ("frameAgeMs", "frame_age_ms")))
        publication_age = self._frame_age_at_publication(snap, _mono_ms(), _perf_ms())
        if frame_age is None:
            unavailable.append("frameAgeMs.atInferenceStart")
        if publication_age is None:
            unavailable.append("frameAgeMs.atPublication")
        return {
            "available": True,
            "schemaVersion": SCHEMA_VERSION,
            "cameraId": camera_id,
            "frameAgeMs": {
                "atInferenceStart": round(frame_age, 3) if frame_age is not None else None,
                "atPublication": round(publication_age, 3) if publication_age is not None else None,
                "atDisplay": None,
                "clockSource": snap.get("frameAgeClockSource") or snap.get("frame_age_clock_source"),
                "atDisplayNote": "computed in the browser as (ui-epoch - backend wall-epoch); cross-clock estimate, not monotonic",
            },
            "stageMs": stages,
            "queues": queues,
            "counters": counters | {
                "processRunId": snap.get("processRunId") or snap.get("process_run_id"),
                "workerPid": snap.get("workerPid") or snap.get("worker_pid"),
                "inferenceGeneration": int(generation) if (generation := _non_negative(
                    snap.get("inferenceGeneration") or snap.get("inference_generation"))) is not None else None,
            },
            "inferenceComputeSynced": boolean if isinstance(boolean, bool) else None,
            "processingLatencyMs": _non_negative(_first_present(snap, ("processing_latency_ms", "latencyMs"))),
            "processingLatencyClockDomain": "worker-monotonic (capture->result build; NOT glass-to-alert)",
            "unavailable": unavailable,
        }

    # ── resource sampling ────────────────────────────────────────────────────
    def sample_resources(self, *, force: bool = False) -> dict:
        if os.getenv("AI_SENTINEL_DISABLE_GPU_SAMPLER", "").strip() in ("1", "true", "yes"):
            gpu, gpu_source, gpu_error = None, "disabled", "AI_SENTINEL_DISABLE_GPU_SAMPLER is set"
        else:
            now = _perf_ms()
            if not force and self._last_resource_sample_perf_ms is not None and \
                    now - self._last_resource_sample_perf_ms < self._resource_ttl_ms:
                return dict(self._resources)
            gpu, gpu_source, gpu_error = self._sample_gpu()
        rss, rss_source = self._sample_rss()
        cpu, cpu_source, cpu_error = self._sample_cpu()
        sample = {
            "processRssBytes": rss,
            "processRssSource": rss_source,
            "cpuPercent": cpu,
            "cpuPercentSource": cpu_source,
            "gpuMemoryUsedBytes": gpu.get("gpuMemoryUsedBytes") if gpu else None,
            "gpuMemoryTotalBytes": gpu.get("gpuMemoryTotalBytes") if gpu else None,
            "gpuUtilPercent": gpu.get("gpuUtilPercent") if gpu else None,
            "gpuScope": "device-wide (nvidia-smi/pynvml device totals; NOT per-process VRAM)",
            "gpuPerProcess": "unavailable: per-process VRAM is measured by WT-16 per processRunId, not here",
            "contentionNote": ("device-wide GPU values may include other workloads; a measured run taken while "
                               "another workload held RESOURCE-LOCK is CONTENDED/INVALID and must be re-run "
                               "(campaign lock protocol)"),
            "resourceSamplerSource": gpu_source if gpu else rss_source,
            "sampledAtMonoMs": round(_mono_ms(), 1),
            "sampledAtPerfMs": round(_perf_ms(), 1),
            "sampledAtEpochMs": round(time.time() * 1000.0, 1),
            "errors": [message for message in (rss_source if rss is None else None,
                                               cpu_error if cpu is None else None,
                                               gpu_error if gpu is None else None) if message],
        }
        with self._lock:
            self._resources = sample
            self._last_resource_sample_perf_ms = _perf_ms()
        if rss is None and cpu is None and gpu is None:
            self.set_subsystem_health("resource-sampler", "UNAVAILABLE",
                                      "; ".join(sample["errors"]) or "no resource source available")
        else:
            self.set_subsystem_health("resource-sampler", "OK", "")
        return sample

    @staticmethod
    def _sample_rss() -> Tuple[Optional[int], Optional[str]]:
        try:
            import psutil  # type: ignore
            return int(psutil.Process().memory_info().rss), "psutil"
        except Exception:
            pass
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                class _ProcessMemoryCounters(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                    ]

                counters = _ProcessMemoryCounters()
                size = ctypes.sizeof(_ProcessMemoryCounters)
                ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                    ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), size)
                if ok:
                    return int(counters.WorkingSetSize), "ctypes-GetProcessMemoryInfo"
                return None, "ctypes-GetProcessMemoryInfo failed"
            except Exception as exc:
                return None, f"rss unavailable: {type(exc).__name__}: {exc}"
        return None, "rss unavailable: no psutil and non-Windows host"

    @staticmethod
    def _sample_cpu() -> Tuple[Optional[float], Optional[str], Optional[str]]:
        try:
            import psutil  # type: ignore
            return float(psutil.Process().cpu_percent(interval=None)), "psutil", None
        except Exception as exc:
            return None, "unavailable", f"cpu unavailable: {type(exc).__name__}: {exc}"

    @staticmethod
    def _sample_gpu() -> Tuple[Optional[dict], str, Optional[str]]:
        try:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                return ({"gpuMemoryUsedBytes": int(memory.used),
                         "gpuMemoryTotalBytes": int(memory.total),
                         "gpuUtilPercent": float(utilization.gpu)}, "pynvml", None)
            finally:
                pynvml.nvmlShutdown()
        except Exception:
            pass
        try:
            completed = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3.0, check=False)
            if completed.returncode == 0 and completed.stdout.strip():
                parts = [part.strip() for part in completed.stdout.strip().splitlines()[0].split(",")]
                return ({"gpuMemoryUsedBytes": int(float(parts[0]) * 1024 * 1024),
                         "gpuMemoryTotalBytes": int(float(parts[1]) * 1024 * 1024),
                         "gpuUtilPercent": float(parts[2])}, "nvidia-smi", None)
            return None, "unavailable", f"nvidia-smi exit {completed.returncode}: {completed.stderr.strip()[:160]}"
        except Exception as exc:
            return None, "unavailable", f"gpu sampler unavailable: {type(exc).__name__}: {exc}"

    # ── faults / health ──────────────────────────────────────────────────────
    def _record_fault(self, kind: str, detail: str) -> None:
        with self._lock:
            self._faults[kind] = int(self._faults.get(kind, 0)) + 1
            self._fault_log.append({"kind": kind, "detail": detail[:300],
                                    "atEpochMs": round(time.time() * 1000.0, 1)})

    def _telemetry_subsystem_health(self) -> Dict[str, dict]:
        stages = self._stage_windows
        def measured(*keys: str) -> bool:
            return any(len(stages.get(key, ())) > 0 for key in keys)
        derived = {
            "telemetry-ingest": {
                "status": "OK" if self._observation.get("ingestCount") else "UNMEASURED",
                "reason": "" if self._observation.get("ingestCount") else
                "no detection snapshot ingested yet: subscribe to /detections or poll /system/status",
            },
            "stage-timings": {
                "status": "OK" if measured("preprocess", "enqueueToDequeue", "inferenceCompute", "inferenceWait")
                else "UNMEASURED",
                "reason": "" if measured("preprocess", "enqueueToDequeue", "inferenceCompute", "inferenceWait")
                else "producer stage fields not present in the result dict yet",
            },
            "frame-age": {
                "status": "OK" if measured("frameAgeAtInferenceStart", "frameAgeAtPublication") else "UNMEASURED",
                "reason": "" if measured("frameAgeAtInferenceStart", "frameAgeAtPublication")
                else "frameAgeMs/capture_timestamp not present on snapshots",
            },
            "queue-telemetry": {
                "status": "OK" if self._queues else "UNMEASURED",
                "reason": "" if self._queues else "no frame/result queue counters observed (R-2)",
            },
            "decision-timing": {
                "status": "OK" if self._decision.get("state") else "UNMEASURED",
                "reason": "" if self._decision.get("state") else "no alert_state observed on snapshots",
            },
            "counter-integrity": {
                "status": "DEGRADED" if (self._faults.get("counterRegressionDetected", 0)
                                         or self._faults.get("nonMonotoneSequenceDetected", 0)) else "OK",
                "reason": "counter/identity regressions observed; see faults" if (
                    self._faults.get("counterRegressionDetected", 0)
                    or self._faults.get("nonMonotoneSequenceDetected", 0)) else "",
            },
        }
        with self._lock:
            merged = dict(derived)
            for name, entry in self._subsystems.items():
                merged[name] = {**entry, "derived": False}
            for name, entry in derived.items():
                merged.setdefault(name, entry)
                merged[name].setdefault("derived", True)
            return merged

    def subsystems(self) -> dict:
        """G-10: every telemetry subsystem exposes explicit health."""
        return self._telemetry_subsystem_health()

    # ── export ───────────────────────────────────────────────────────────────
    def export_snapshot(self, *, run_provenance: Optional[dict] = None) -> dict:
        resources = self.sample_resources()
        with self._lock:
            stage_payload: Dict[str, dict] = {}
            for key, window in self._stage_windows.items():
                model = self._stage_models.get(key)
                stage = key.split(":", 1)[1] if model and key.startswith(f"{model}:") else key
                entry = _distribution(window, "ms", clock_domain=self._stage_clock.get(key),
                                      synced=self._stage_sync.get(key))
                if entry is None:
                    continue
                if key in self._stage_cuda_sync:
                    entry["cudaSyncApplied"] = self._stage_cuda_sync[key]
                if model:
                    entry["model"] = model
                # group by stage; per-model stages nest under models
                bucket = stage_payload.setdefault(stage, {"byModel": {}})
                if model:
                    bucket["byModel"][model] = entry
                else:
                    bucket.update(entry)
            rates = {
                "captureFps": _rate(self._reported_rates.get("captureFps", deque()), source="producer-reported")
                or _distribution(self.capture_fps, "fps"),
                "renderFps": _rate(self._reported_rates.get("renderFps", deque()), source="producer-reported")
                or _distribution(self.stream_fps, "fps"),
                "publicationFps": _rate(self._counter_windows.get("publicationCount", deque()),
                                        source="computed-from-publication-counter", counter=True),
                "completedInferenceFps": {
                    model: _rate(self._counter_windows.get(f"{model}CompletedCount", deque()),
                                 source="computed-from-completed-inference-counter", counter=True)
                    for model in ("person", "violence", "weapon")
                },
            }
            counters = {name: dict(entry) for name, entry in self._counters.items()}
            queues: Dict[str, dict] = {}
            for name, entry in self._queues.items():
                depth_dist = _distribution(entry["depthSamples"], "frames")
                dropped = entry.get("droppedTotal")
                derived = entry.get("derivedDroppedTotal")
                divergence = None
                if dropped is not None and derived is not None:
                    divergence = abs(int(dropped) - int(derived))
                baseline_value = entry.get("droppedBaselineValue")
                baseline_ms = entry.get("droppedBaselineAtPerfMs")
                drop_rate = None
                if dropped is not None and baseline_value is not None and baseline_ms is not None:
                    elapsed = (entry.get("lastAtPerfMs") or baseline_ms) - baseline_ms
                    if elapsed > 0:
                        drop_rate = round((int(dropped) - int(baseline_value)) / (elapsed / 1000.0), 4)
                queues[name] = {
                    "depthNow": entry.get("depthNow"),
                    "depthDist": depth_dist,
                    "droppedTotal": dropped,
                    "droppedDerivedTotal": derived,
                    "divergenceFlag": divergence if divergence is None or divergence > 0 else 0,
                    "divergence": divergence,
                    "dropRatePerSec": drop_rate,
                    "dropRateClockDomain": "perf-counter",
                    "producer": entry.get("producer"),
                    "lastAtPerfMs": entry.get("lastAtPerfMs"),
                    "note": "dropRatePerSec is measured from the first observed drop baseline in this process run",
                }
            decision = {
                "state": self._decision.get("state"),
                "stateSinceMonoMs": self._decision.get("stateSinceMonoMs"),
                "transitions": list(self._decision.get("transitions", [])),
                "confirmLatencyMs": _distribution(self._decision.get("confirmLatencySamples", deque()), "ms",
                                                  clock_domain="decision-sample-clock"),
                "confirmLatencyClock": self._decision.get("confirmLatencyClock"),
                "confirmLatencyNote": ("producer-supplied CONFIRMED latency (WT-20: window-open->confirmed on the "
                                       "decision sample clock; measured, None until a confirmation happens and after "
                                       "reset). NOT glass-to-alert."),
                "observedFromSnapshots": True,
            }
            observation = dict(self._observation)
            faults = dict(self._faults)
            fault_log = list(self._fault_log)
            provenance = dict(self._run_provenance)
            if run_provenance:
                provenance.update(run_provenance)
            if not provenance:
                provenance = {"label": "unlabeled",
                              "note": "no run provenance supplied; consumers must not assume a clean adapter state (B-3)"}
            last_ingest = self._last_ingest_mono_ms
            stage_clock_map = dict(getattr(self, "_stage_clock", {}))
            subsystems = self._telemetry_subsystem_health()
        return {
            "schemaVersion": SCHEMA_VERSION,
            "generatedAtEpochMs": round(time.time() * 1000.0, 1),
            "generatedAtMonoMs": round(_mono_ms(), 1),
            "generatedAtPerfMs": round(_perf_ms(), 1),
            "clockQuantization": dict(_CLOCK_QUANTIZATION),
            "clockDomains": CLOCK_DOMAINS,
            "fieldNaming": FIELD_NAMING,
            "rules": EXPORT_RULES,
            "runProvenance": provenance,
            "ingest": {
                "surfaces": ["GET /detections", "GET /system/status"],
                "lastIngestAtMonoMs": round(last_ingest, 1) if last_ingest is not None else None,
                "hint": "poll /system/status or keep a /detections subscription open; otherwise counters stay unmeasured",
            },
            "observation": observation,
            "crossProcessClockComparability": {
                "sameMachineQpc": "assumed (Windows QPC is system-wide); under empirical verification by WT-15",
                "rule": "cross-boundary ages are derived only on the producer-declared captureClockBase",
            },
            "sampling": {
                "distributionWindowMaxlen": WINDOW_MAXLEN,
                "rateWindowMaxlen": RATE_WINDOW_MAXLEN,
                "note": "distributions keep the most recent n samples per stage; n is the denominator actually measured",
            },
            "rates": rates,
            "frameAgeMs": {
                "atInferenceStart": stage_payload.get("frameAgeAtInferenceStart"),
                "atPublication": stage_payload.get("frameAgeAtPublication"),
                "atDisplay": {
                    "status": "unavailable",
                    "reason": "browser-side: computed by the UI as (ui-epoch - backend updatedAt wall-epoch); cross-clock estimate",
                },
            },
            "backlogFrames": stage_payload.get("backlogFrames"),
            "stageLatencyMs": {key: value for key, value in stage_payload.items()
                               if key not in ("frameAgeAtInferenceStart", "frameAgeAtPublication", "backlogFrames",
                                              "decisionStateDuration")},
            "decisionStateDurationMs": stage_payload.get("decisionStateDuration"),
            "queues": queues,
            "counters": counters,
            "models": {
                model: {
                    "completedCount": (counters.get(f"{model}CompletedCount") or {}).get("value"),
                    "completedInferenceFps": rates["completedInferenceFps"].get(model),
                } for model in ("person", "violence", "weapon")
            },
            "capture": dict(self._capture_health),
            "resources": resources,
            "decision": decision,
            "faults": faults,
            "faultLog": fault_log,
            "subsystems": subsystems,
            "stageClockDomains": stage_clock_map,
        }

    def summary(self) -> dict:
        """Legacy summary keys (unchanged) plus the additive telemetry export."""
        def avg(values: Deque) -> float:
            return sum(values) / len(values) if values else 0.0
        legacy = {
            "captureFps": round(avg(self.capture_fps), 1),
            "inferenceLatencyMs": round(avg(self.inference_latency_ms), 1),
            "encodeLatencyMs": round(avg(self.encode_latency_ms), 1),
            "streamFps": round(avg(self.stream_fps), 1),
            "avgWeaponScore": round(avg(self.weapon_score), 3),
            "avgPersonCount": round(avg(self.person_count), 1),
        }
        export = self.export_snapshot()
        telemetry = {
            "schemaVersion": export["schemaVersion"],
            "rates": export["rates"],
            "frameAgeMs": export["frameAgeMs"],
            "queues": export["queues"],
            "faults": export["faults"],
            "subsystems": export["subsystems"],
            "resources": export["resources"],
            "observation": export["observation"],
        }
        return {**legacy, "telemetry": telemetry, "metricsExport": export}


pipeline_metrics = PipelineMetrics()
