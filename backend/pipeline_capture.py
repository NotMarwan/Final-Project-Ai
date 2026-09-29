"""Dedicated capture thread — reads frames from video source at source FPS.

WT-14 capture-quality contracts (see config/camera_profiles.yml for the schema):

* Capture mode negotiation: the thread PINs an explicit backend (CAP_DSHOW /
  CAP_MSMF for USB devices, CAP_FFMPEG for network streams), requests
  1280x720@30 MJPG with a YUY2 fallback, then READS THE MODE BACK and asserts
  it against the request.  The OS can silently swap MJPEG for decoded
  NV12/YUY2 (Windows "MJPEG at source autodecode"); a mismatch is NEVER
  silent: it lands on the F-38 health surface as DEGRADED with the exact
  requested-vs-actual values and an exact log line.
* Freshness: live network sources read through _drain_to_latest
  (latest-frame-wins; grab-drain-retrieve).  Reconnect uses exponential
  backoff with jitter (1s -> 2s -> 4s ... 30s cap), never a fixed sleep.
* Evidence ring: frames are stored as EvidenceFrame records in one of three
  formats — raw BGR (exact), jpeg90 or NV12 (compressed, decode-at-assembly).
  Ring payloads NEVER alias the capture buffer and derived inference views
  NEVER alias evidence payloads (regression-pinned in
  backend/tests/test_evidence_ring_aliasing.py).
* Stats (canonical camelCase names locked with WT-13/WT-15):
  framesReadCount, duplicateFrameCount, reconnectCount,
  readGapP50Ms/readGapP95Ms/readGapMaxMs/readGapSampleCount,
  stageFrameReadP50Ms/stageFrameReadP95Ms/stageFrameReadSampleCount,
  frameQueueDropped, frameQueueDepth.

This thread NEVER blocks on AI inference. It reads frames as fast as the
source provides them and pushes to a bounded queue. If the queue is full
(AI is slower than capture), the NEWEST frame is dropped and COUNTED
(frameQueueDropped; runtime-map R-2 closure) — never silently.
"""
from __future__ import annotations

import logging
import os
import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Clock base (WT-15 ASK C).  captured_at is only ever DIFFED inside a single
# base; the active base is published so cross-process consumers (frame age,
# incident sweeps) diff within the same clock family.  Default "monotonic"
# keeps deployed SC-6 semantics; "perf-qpc" opts into QPC resolution for
# measurement runs.
# ---------------------------------------------------------------------------
VALID_CLOCK_BASES = ("monotonic-gettickcount64", "perf-qpc")
CLOCK_BASE_ALIASES = {"monotonic": "monotonic-gettickcount64"}
_capture_clock_base = "monotonic-gettickcount64"


def set_capture_clock_base(base: str) -> str:
    global _capture_clock_base
    canonical = CLOCK_BASE_ALIASES.get(base, base)
    if canonical not in VALID_CLOCK_BASES:
        raise ValueError(f"Unsupported capture clock base: {base!r}")
    _capture_clock_base = canonical
    return _capture_clock_base


def get_capture_clock_base() -> str:
    return _capture_clock_base


def capture_now() -> float:
    """Monotonic stamp for capture-side timestamps (read-complete semantics)."""
    return time.perf_counter() if _capture_clock_base == "perf-qpc" else time.monotonic()


def fourcc_str(code: Union[int, float, None]) -> str:
    """Decode a FOURCC int to a printable 4-char tag (e.g. 1196444237 -> MJPG)."""
    if code is None:
        return "NONE"
    try:
        value = int(code)
    except (TypeError, ValueError):
        return "NONE"
    if value <= 0:
        return "NONE"
    raw = value.to_bytes(4, "little", signed=False)
    tag = "".join(chr(b) if 32 <= b < 127 else "?" for b in raw)
    return tag


def fourcc_code(tag: str) -> int:
    padded = (tag.upper() + "    ")[:4]
    return int.from_bytes(padded.encode("ascii", "replace"), "little")


BACKEND_APIS = {
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
    "ffmpeg": cv2.CAP_FFMPEG,
    "any": cv2.CAP_ANY,
}


# ---------------------------------------------------------------------------
# Camera profile (config/camera_profiles.yml; additive to the legacy
# `cameras:` source map consumed by api._load_profile_camera_sources).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CaptureRequest:
    width: int = 1280
    height: int = 720
    fps: float = 30.0
    fourcc: str = "MJPG"
    fallback_fourcc: str = "YUY2"


@dataclass(frozen=True)
class RingConfig:
    max_side: int = 960
    seconds: float = 5.0
    format: str = "bgr"            # bgr | jpeg90 | nv12
    jpeg_quality: int = 90
    max_entries: int = 600


@dataclass(frozen=True)
class ReconnectConfig:
    initial_delay_s: float = 1.0
    max_delay_s: float = 30.0
    multiplier: float = 2.0
    jitter: float = 0.2            # +/- fraction of the computed delay


@dataclass(frozen=True)
class DegradationStep:
    jpeg_quality: Optional[int] = None
    ring_fps: Optional[float] = None
    ring_max_side: Optional[int] = None
    pause_annotation: bool = False


@dataclass(frozen=True)
class DegradationConfig:
    enabled: bool = False
    degrade_after_s: float = 5.0
    recover_after_s: float = 30.0
    steps: Tuple[DegradationStep, ...] = ()


@dataclass(frozen=True)
class CaptureProfile:
    camera_id: str = "CAM-00"
    backend: str = "dshow"
    request: CaptureRequest = field(default_factory=CaptureRequest)
    verify_mode: bool = True
    drain_to_latest: bool = True
    drain_budget_s: float = 0.004
    max_drain: int = 30
    ring: RingConfig = field(default_factory=RingConfig)
    reconnect: ReconnectConfig = field(default_factory=ReconnectConfig)
    degradation: DegradationConfig = field(default_factory=DegradationConfig)
    priority: int = 1

    @property
    def acceptable_fourccs(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys((self.request.fourcc, self.request.fallback_fourcc)))


RING_FORMATS = ("bgr", "jpeg90", "nv12")


def _coerce_request(raw: Any) -> CaptureRequest:
    if not isinstance(raw, dict):
        return CaptureRequest()
    return CaptureRequest(
        width=int(raw.get("width", 1280)),
        height=int(raw.get("height", 720)),
        fps=float(raw.get("fps", 30.0)),
        fourcc=str(raw.get("fourcc", "MJPG")).upper(),
        fallback_fourcc=str(raw.get("fallback_fourcc", "YUY2")).upper(),
    )


def _coerce_ring(raw: Any) -> RingConfig:
    if not isinstance(raw, dict):
        return RingConfig()
    fmt = str(raw.get("format", "bgr")).lower()
    if fmt not in RING_FORMATS:
        raise ValueError(f"Unsupported ring format: {fmt!r} (expected one of {RING_FORMATS})")
    return RingConfig(
        max_side=int(raw.get("max_side", 960)),
        seconds=float(raw.get("seconds", 5.0)),
        format=fmt,
        jpeg_quality=int(raw.get("jpeg_quality", 90)),
        max_entries=int(raw.get("max_entries", 600)),
    )


def _coerce_reconnect(raw: Any) -> ReconnectConfig:
    if not isinstance(raw, dict):
        return ReconnectConfig()
    return ReconnectConfig(
        initial_delay_s=float(raw.get("initial_delay_s", 1.0)),
        max_delay_s=float(raw.get("max_delay_s", 30.0)),
        multiplier=float(raw.get("multiplier", 2.0)),
        jitter=float(raw.get("jitter", 0.2)),
    )


def _coerce_degradation(raw: Any) -> DegradationConfig:
    if not isinstance(raw, dict):
        return DegradationConfig()
    steps_raw = raw.get("steps") or ()
    steps = []
    for item in steps_raw:
        if not isinstance(item, dict):
            continue
        steps.append(DegradationStep(
            jpeg_quality=int(item["jpeg_quality"]) if "jpeg_quality" in item else None,
            ring_fps=float(item["ring_fps"]) if "ring_fps" in item else None,
            ring_max_side=int(item["ring_max_side"]) if "ring_max_side" in item else None,
            pause_annotation=bool(item.get("pause_annotation", False)),
        ))
    return DegradationConfig(
        enabled=bool(raw.get("enabled", False)),
        degrade_after_s=float(raw.get("degrade_after_s", 5.0)),
        recover_after_s=float(raw.get("recover_after_s", 30.0)),
        steps=tuple(steps),
    )


def _coerce_profile(camera_id: str, raw: Any) -> CaptureProfile:
    if not isinstance(raw, dict):
        raw = {}
    backend = str(raw.get("backend", "dshow")).lower()
    if backend not in BACKEND_APIS:
        raise ValueError(f"Unsupported capture backend: {backend!r} (expected one of {tuple(BACKEND_APIS)})")
    return CaptureProfile(
        camera_id=camera_id,
        backend=backend,
        request=_coerce_request(raw.get("request")),
        verify_mode=bool(raw.get("verify_mode", True)),
        drain_to_latest=bool(raw.get("drain_to_latest", True)),
        drain_budget_s=float(raw.get("drain_budget_s", 0.004)),
        max_drain=int(raw.get("max_drain", 30)),
        ring=_coerce_ring(raw.get("ring")),
        reconnect=_coerce_reconnect(raw.get("reconnect")),
        degradation=_coerce_degradation(raw.get("degradation")),
        priority=int(raw.get("priority", 1)),
    )


def load_capture_profiles(path: Union[str, "os.PathLike[str]"]) -> Dict[str, CaptureProfile]:
    """Parse config/camera_profiles.yml into per-camera CaptureProfile values.

    Unknown keys are ignored so the legacy source-map keys (source/rtsp/
    enabled) keep working in the same document.
    """
    import yaml

    with open(path, "r", encoding="utf-8") as handle:
        doc = yaml.safe_load(handle) or {}
    cameras = doc.get("cameras")
    if not isinstance(cameras, dict):
        return {}
    profiles: Dict[str, CaptureProfile] = {}
    for camera_id, payload in cameras.items():
        if isinstance(camera_id, str) and isinstance(payload, dict):
            profiles[camera_id] = _coerce_profile(camera_id, payload)
    return profiles


def default_profile(camera_id: str = "CAM-00") -> CaptureProfile:
    return CaptureProfile(camera_id=camera_id)


# ---------------------------------------------------------------------------
# Evidence ring records (F-21/F-22 frame storage; SC-8 assembly unchanged).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidenceFrame:
    captured_at: float
    payload: Any                 # np.ndarray BGR | bytes (jpeg) | np.ndarray NV12
    fmt: str                     # bgr | jpeg90 | nv12
    sequence: int
    width: int
    height: int

    @property
    def nbytes(self) -> int:
        payload = self.payload
        return int(payload.nbytes) if hasattr(payload, "nbytes") else len(payload)


def _encode_jpeg(frame: np.ndarray, quality: int) -> bytes:
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        raise ValueError("JPEG encode failed for evidence frame")
    return buf.tobytes()


def _bgr_to_nv12(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420).reshape(
        (frame.shape[0] * 3 // 2, frame.shape[1])
    )


def _nv12_to_bgr(frame: np.ndarray) -> np.ndarray:
    height = frame.shape[0] * 2 // 3
    yuv = frame.reshape((height * 3 // 2, frame.shape[1]))
    return cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)


def make_evidence_frame(
    view: np.ndarray,
    source: Optional[np.ndarray],
    fmt: str,
    captured_at: float,
    sequence: int,
    jpeg_quality: int = 90,
) -> EvidenceFrame:
    """Build a ring record from a (possibly derived) view of the capture frame.

    For fmt == "bgr" the record MUST own its buffer: if `view` is `source`
    itself (downscale passthrough — no resize happened) it is copied here so
    the ring can never alias the capture buffer.  Resize outputs are already
    fresh buffers and are stored as-is (zero avoidable copies).
    """
    if fmt not in RING_FORMATS:
        raise ValueError(f"Unsupported evidence format: {fmt!r}")
    height, width = view.shape[:2]
    if fmt == "bgr":
        if view is source or (source is not None and view.base is source):
            view = view.copy()
        payload: Any = view
    elif fmt == "jpeg90":
        payload = _encode_jpeg(view, jpeg_quality)
    else:
        payload = _bgr_to_nv12(view)
    return EvidenceFrame(
        captured_at=float(captured_at),
        payload=payload,
        fmt=fmt,
        sequence=int(sequence),
        width=int(width),
        height=int(height),
    )


def decode_evidence_frame(entry: EvidenceFrame) -> np.ndarray:
    """Decode a ring record back to BGR for clip assembly (evidence path).

    bgr records are returned as the stored array — callers MUST NOT mutate
    (clip assembly only reads; ROI/zoom work happens on copies).
    """
    if entry.fmt == "bgr":
        return entry.payload
    if entry.fmt == "jpeg90":
        buf = np.frombuffer(entry.payload, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError(f"Evidence JPEG decode failed for sequence {entry.sequence}")
        return frame
    return _nv12_to_bgr(entry.payload)


def iter_evidence_frames(entries: Iterable[EvidenceFrame]) -> Iterable[np.ndarray]:
    for entry in entries:
        yield decode_evidence_frame(entry)


def fit_evidence_frame(frame: np.ndarray, canvas_w: int, canvas_h: int) -> Tuple[np.ndarray, bool]:
    """Fit a decoded frame to the assembly canvas WITHOUT upscaling content.

    Equal size -> identity (zero copies).  Larger -> INTER_AREA downscale
    (allowed).  Smaller -> letterbox pad on black (content pixels untouched —
    never an upscale claim).  Returns (frame, adjusted).
    """
    height, width = frame.shape[:2]
    if width == canvas_w and height == canvas_h:
        return frame, False
    if width > canvas_w or height > canvas_h:
        scale = min(canvas_w / width, canvas_h / height)
        fitted = cv2.resize(
            frame,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        fitted = frame
    height, width = fitted.shape[:2]
    pad_top = (canvas_h - height) // 2
    pad_left = (canvas_w - width) // 2
    padded = cv2.copyMakeBorder(
        fitted, pad_top, canvas_h - height - pad_top,
        pad_left, canvas_w - width - pad_left,
        cv2.BORDER_CONSTANT, value=(0, 0, 0),
    )
    return padded, True


def materialize_evidence_samples(entries: Sequence[EvidenceFrame]) -> Tuple[List[Tuple[float, np.ndarray]], int]:
    """Decode ring records to (captured_at, bgr) tuples for encode_browser_mp4.

    Runs on the evidence writer thread (decode-at-assembly ~3.4 ms/frame
    measured, WT-10 P-3), never on the capture or alert dispatch path.
    Mixed record sizes (ring max-side ladder step mid-window) are fitted to
    the FIRST record's canvas without upscaling; returns (samples, adjusted).
    """
    samples: List[Tuple[float, np.ndarray]] = []
    adjusted = 0
    canvas: Optional[Tuple[int, int]] = None
    for entry in entries:
        frame = decode_evidence_frame(entry)
        if canvas is None:
            canvas = (entry.width, entry.height)
        frame, changed = fit_evidence_frame(frame, canvas[0], canvas[1])
        if changed:
            adjusted += 1
        samples.append((entry.captured_at, frame))
    return samples, adjusted


class DecodedPostQueue:
    """Adapter: post-event queue of EvidenceFrame records -> (stamp, frame) tuples.

    api._write_evidence_clip keeps its exact (stamp, frame) contract; decoding
    happens lazily on the writer thread as items arrive, so the compressed
    post window costs ~22 MiB instead of ~534 MiB (WT-10 §3.2).
    """

    def __init__(self, inner, canvas: Optional[Tuple[int, int]] = None):
        self._inner = inner
        self._canvas = canvas
        self.adjusted = 0

    def get(self, timeout: Optional[float] = None):
        import queue as _queue
        try:
            item = self._inner.get(timeout=timeout) if timeout is not None else self._inner.get()
        except _queue.Empty:
            raise
        if item is None or isinstance(item, tuple):
            return item
        frame = decode_evidence_frame(item)
        if self._canvas is None:
            self._canvas = (item.width, item.height)
        frame, changed = fit_evidence_frame(frame, self._canvas[0], self._canvas[1])
        if changed:
            self.adjusted += 1
        return (item.captured_at, frame)

    def put_nowait(self, item):
        self._inner.put_nowait(item)

    def qsize(self) -> int:
        return self._inner.qsize()


def copy_if_aliased(view: np.ndarray, source: np.ndarray) -> np.ndarray:
    """Return an independent buffer when a downscale passthrough aliased `source`."""
    return view.copy() if (view is source or view.base is source) else view


# ---------------------------------------------------------------------------
# Capture statistics (F-38 surface; names locked with WT-13 MeasurementTelemetry)
# ---------------------------------------------------------------------------
@dataclass
class CaptureStats:
    frames_read: int = 0
    duplicate_frames: int = 0
    reconnects: int = 0
    evidence_frames_decimated: int = 0
    evidence_frames_adjusted: int = 0
    frame_queue_dropped: int = 0
    frame_queue_depth: int = 0
    read_gaps_ms: deque = field(default_factory=lambda: deque(maxlen=240))
    frame_read_ms: deque = field(default_factory=lambda: deque(maxlen=240))

    @staticmethod
    def _percentile(samples: Sequence[float], q: float) -> float:
        if not samples:
            return 0.0
        ordered = sorted(samples)
        index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
        return float(ordered[index])

    def snapshot(self) -> dict:
        gaps = list(self.read_gaps_ms)
        reads = list(self.frame_read_ms)
        return {
            "framesReadCount": self.frames_read,
            "duplicateFrameCount": self.duplicate_frames,
            "reconnectCount": self.reconnects,
            "readGapP50Ms": round(self._percentile(gaps, 0.50), 3),
            "readGapP95Ms": round(self._percentile(gaps, 0.95), 3),
            "readGapMaxMs": round(max(gaps), 3) if gaps else 0.0,
            "readGapSampleCount": len(gaps),
            "stageFrameReadP50Ms": round(self._percentile(reads, 0.50), 3),
            "stageFrameReadP95Ms": round(self._percentile(reads, 0.95), 3),
            "stageFrameReadSampleCount": len(reads),
            "frameQueueDropped": self.frame_queue_dropped,
            "frameQueueDepth": self.frame_queue_depth,
            "evidenceFramesDecimated": self.evidence_frames_decimated,
            "evidenceFramesAdjusted": self.evidence_frames_adjusted,
        }


def bounded_put_drop_newest(frame_queue, packet, stats: CaptureStats) -> bool:
    """Bounded put that COUNTS drops (runtime-map R-2 closure).

    Drop-NEWEST policy preserved; if WT-15 measurement verdicts drop-OLDEST,
    this helper is the single site that changes.
    """
    import queue as _queue
    try:
        frame_queue.put_nowait(packet)
        try:
            stats.frame_queue_depth = int(frame_queue.qsize())
        except (NotImplementedError, AttributeError):
            pass
        return True
    except _queue.Full:
        stats.frame_queue_dropped += 1
        return False


# ---------------------------------------------------------------------------
# Negotiated-mode read-back (F-03/F-38)
# ---------------------------------------------------------------------------
@dataclass
class NegotiatedMode:
    requested: Dict[str, Any]
    actual: Dict[str, Any]
    mismatched_fields: Tuple[str, ...]
    fallback_used: bool
    backend: str

    @property
    def mismatch(self) -> bool:
        return bool(self.mismatched_fields)

    def describe(self) -> str:
        req = self.requested
        act = self.actual
        return (
            f"requested={req['width']}x{req['height']}@{req['fps']:.1f} {req['fourcc']} "
            f"actual={act['width']}x{act['height']}@{act['fps']:.1f} {act['fourcc']}"
        )

    def to_dict(self) -> dict:
        return {
            "requestedWidth": self.requested["width"],
            "requestedHeight": self.requested["height"],
            "requestedFps": round(float(self.requested["fps"]), 3),
            "requestedFourcc": self.requested["fourcc"],
            "negotiatedWidth": self.actual["width"],
            "negotiatedHeight": self.actual["height"],
            "negotiatedFps": round(float(self.actual["fps"]), 3),
            "negotiatedFourcc": self.actual["fourcc"],
            "modeMismatch": self.mismatch,
            "mismatchedFields": list(self.mismatched_fields),
            "fallbackUsed": self.fallback_used,
            "captureBackend": self.backend,
        }


def verify_negotiated_mode(
    profile: CaptureProfile,
    actual: Dict[str, Any],
    backend: str,
) -> NegotiatedMode:
    """Compare read-back properties against the request (fps tolerance 1%)."""
    req = {
        "width": profile.request.width,
        "height": profile.request.height,
        "fps": profile.request.fps,
        "fourcc": profile.request.fourcc,
    }
    acceptable = profile.acceptable_fourccs
    mismatched: List[str] = []
    if int(actual.get("width", 0)) != req["width"]:
        mismatched.append("width")
    if int(actual.get("height", 0)) != req["height"]:
        mismatched.append("height")
    actual_fps = float(actual.get("fps", 0.0) or 0.0)
    if req["fps"] > 0 and (actual_fps <= 0 or abs(actual_fps - req["fps"]) > max(0.5, 0.01 * req["fps"])):
        mismatched.append("fps")
    actual_fourcc = str(actual.get("fourcc", "NONE")).upper()
    if actual_fourcc not in acceptable:
        mismatched.append("fourcc")
    return NegotiatedMode(
        requested=req,
        actual={
            "width": int(actual.get("width", 0)),
            "height": int(actual.get("height", 0)),
            "fps": actual_fps,
            "fourcc": actual_fourcc,
        },
        mismatched_fields=tuple(mismatched),
        fallback_used=(actual_fourcc == profile.request.fallback_fourcc),
        backend=backend,
    )


# ---------------------------------------------------------------------------
# Reconnect backoff (exponential + jitter; replaces fixed 2s sleep)
# ---------------------------------------------------------------------------
def next_backoff_delay(attempt: int, cfg: ReconnectConfig, rng: Optional[random.Random] = None) -> float:
    """Delay before reconnect attempt N (attempt starts at 1): 1,2,4,...,cap."""
    exponent = max(0, int(attempt) - 1)
    base = cfg.initial_delay_s * (cfg.multiplier ** exponent)
    delay = min(base, cfg.max_delay_s)
    if cfg.jitter > 0:
        r = rng or random
        delay *= 1.0 + r.uniform(-cfg.jitter, cfg.jitter)
    return max(0.0, min(delay, cfg.max_delay_s * (1.0 + cfg.jitter)))


# ---------------------------------------------------------------------------
# Degradation ladder (config-driven; multi-camera pressure)
# ---------------------------------------------------------------------------
class DegradationLadder:
    """Ordered quality ladder: jpeg quality -> ring fps -> ring max-side -> pause annotation.

    Transitions are always counted and logged (evidence-frame decimation is
    surfaced as evidenceFramesDecimated) — the ladder can reduce quality but
    can NEVER lose evidence frames silently.
    """

    def __init__(self, config: DegradationConfig, clock: Callable[[], float] = time.monotonic):
        self.config = config
        self._clock = clock
        self.level = 0
        self.transitions: List[Tuple[float, int, int, str]] = []
        self.step_counts: Dict[str, int] = {}
        self._pressure_since: Optional[float] = None
        self._healthy_since: Optional[float] = None

    def observe(self, healthy: bool, now: Optional[float] = None) -> int:
        if not self.config.enabled or not self.config.steps:
            return self.level
        now = self._clock() if now is None else now
        if healthy:
            self._pressure_since = None
            if self._healthy_since is None:
                self._healthy_since = now
            elif now - self._healthy_since >= self.config.recover_after_s and self.level > 0:
                self._transition(self.level - 1, "recovered")
                self._healthy_since = now
        else:
            self._healthy_since = None
            if self._pressure_since is None:
                self._pressure_since = now
            elif now - self._pressure_since >= self.config.degrade_after_s and self.level < len(self.config.steps):
                self._transition(self.level + 1, "pressure")
                self._pressure_since = now
        return self.level

    def _transition(self, new_level: int, reason: str) -> None:
        old = self.level
        self.level = new_level
        self.transitions.append((self._clock(), old, new_level, reason))
        key = self._step_key(self.config.steps[new_level - 1]) if new_level > old else "recover"
        self.step_counts[key] = self.step_counts.get(key, 0) + 1
        logger.warning(
            "Capture degradation ladder %s -> %s (%s): applied=%s",
            old, new_level, reason, key,
        )

    @staticmethod
    def _step_key(step: DegradationStep) -> str:
        if step.jpeg_quality is not None:
            return f"jpeg_quality:{step.jpeg_quality}"
        if step.ring_fps is not None:
            return f"ring_fps:{step.ring_fps}"
        if step.ring_max_side is not None:
            return f"ring_max_side:{step.ring_max_side}"
        return "pause_annotation"

    def _applied(self) -> Tuple[Optional[int], Optional[float], Optional[int], bool]:
        jpeg_quality = None
        ring_fps = None
        ring_max_side = None
        pause = False
        for step in self.config.steps[: self.level]:
            if step.jpeg_quality is not None:
                jpeg_quality = step.jpeg_quality
            if step.ring_fps is not None:
                ring_fps = step.ring_fps
            if step.ring_max_side is not None:
                ring_max_side = step.ring_max_side
            pause = pause or step.pause_annotation
        return jpeg_quality, ring_fps, ring_max_side, pause

    def ring_config(self, base: RingConfig) -> RingConfig:
        jpeg_quality, ring_fps, ring_max_side, _ = self._applied()
        from dataclasses import replace
        return replace(
            base,
            jpeg_quality=jpeg_quality if jpeg_quality is not None else base.jpeg_quality,
            max_side=ring_max_side if ring_max_side is not None else base.max_side,
        )

    @property
    def pause_annotation(self) -> bool:
        return bool(self._applied()[3])

    def ring_fps_cap(self) -> Optional[float]:
        return self._applied()[1]

    def should_append(self, sequence: int, nominal_fps: float) -> bool:
        cap = self.ring_fps_cap()
        if not cap or nominal_fps <= 0 or cap >= nominal_fps:
            return True
        stride = max(1, int(round(nominal_fps / cap)))
        return (sequence % stride) == 0

    def snapshot(self) -> dict:
        return {
            "degradationLevel": self.level,
            "degradationSteps": dict(self.step_counts),
            "degradationEnabled": self.config.enabled,
        }


# ---------------------------------------------------------------------------
# Capture thread
# ---------------------------------------------------------------------------
class CaptureThread:
    """Producer thread: reads frames from camera/file; never blocks on AI.

    Public surface kept compatible with the api.camera_worker call sites:
    open(), read_frame(), reconnect(), release(), get_props().  New:
    negotiated_mode, stats (CaptureStats), health_details().
    """

    def __init__(
        self,
        source: Union[str, int],
        queue: deque,
        ring_buffer: deque,
        stop_event: threading.Event,
        max_queue_size: int = 5,
        file_skip_frames: int = 0,
        profile: Optional[CaptureProfile] = None,
        clock: Callable[[], float] = capture_now,
    ):
        self.source = source
        self.queue = queue
        self.ring_buffer = ring_buffer
        self.stop_event = stop_event
        self.max_queue_size = max_queue_size
        self.file_skip_frames = file_skip_frames
        self.profile = profile or default_profile()
        self._clock = clock
        self.cap: Optional[cv2.VideoCapture] = None
        self.fps: float = 0.0
        self.width: int = 0
        self.height: int = 0
        self.frame_count: int = 0
        self.stats = CaptureStats()
        self.negotiated: Optional[NegotiatedMode] = None
        self.capture_state: str = "idle"      # ok|partial|mode-mismatch|interrupted|reconnecting
        self._last_read_stamp: Optional[float] = None
        self._prev_fingerprint: Optional[bytes] = None
        self._reconnect_attempt = 0
        # Prerecorded-media timeline (SC-6): the MEDIA frame index of the last
        # returned frame, counting skipped frames. sample_timestamp must ride
        # this index so a skip run can never masquerade as 32 frames @ fps.
        self.next_media_index = 0
        self.last_media_index = 0

    # -- source classification ------------------------------------------------
    def _is_network_live(self) -> bool:
        return isinstance(self.source, str) and self.source.lower().startswith(("rtsp://", "rtmp://", "http://", "https://"))

    def _is_usb_live(self) -> bool:
        return isinstance(self.source, int)

    def _is_live(self) -> bool:
        return self._is_network_live() or self._is_usb_live()

    # -- open / negotiation ----------------------------------------------------
    def _create_capture(self, api: int, params: Sequence[int] = ()) -> cv2.VideoCapture:
        """Seam for tests: construct the backend VideoCapture."""
        if params:
            return cv2.VideoCapture(self.source, api, list(params))
        return cv2.VideoCapture(self.source, api)

    def _read_back_mode(self) -> Dict[str, Any]:
        assert self.cap is not None
        return {
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0),
            "fourcc": fourcc_str(self.cap.get(cv2.CAP_PROP_FOURCC)),
        }

    def _apply_requested_mode(self) -> None:
        """Request 1280x720@30 MJPG with YUY2 fallback on USB devices."""
        assert self.cap is not None
        req = self.profile.request
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, req.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, req.height)
        self.cap.set(cv2.CAP_PROP_FPS, req.fps)
        self.cap.set(cv2.CAP_PROP_FOURCC, fourcc_code(req.fourcc))
        readback = self._read_back_mode()
        if readback["fourcc"] != req.fourcc and req.fallback_fourcc:
            logger.info(
                "Capture fourcc %s not accepted (%s read back); trying fallback %s for %s",
                req.fourcc, readback["fourcc"], req.fallback_fourcc, self.profile.camera_id,
            )
            self.cap.set(cv2.CAP_PROP_FOURCC, fourcc_code(req.fallback_fourcc))

    def open(self) -> bool:
        """Open the source with a PINNED backend and verify the negotiated mode."""
        if self._is_network_live():
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;tcp|"
                "fflags;nobuffer|"
                "flags;low_delay|"
                "max_delay;0|"
                "analyzeduration;100000|"
                "probesize;50000"
            )
            self.cap = self._create_capture(
                cv2.CAP_FFMPEG,
                [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000],
            )
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        elif self._is_usb_live():
            backend_api = BACKEND_APIS.get(self.profile.backend, cv2.CAP_DSHOW)
            self.cap = self._create_capture(backend_api)
            if self.cap.isOpened():
                self._apply_requested_mode()
        else:
            self.cap = self._create_capture(cv2.CAP_ANY)

        if self.cap and self.cap.isOpened():
            self.capture_state = "ok"
            self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if self._is_live() and self.profile.verify_mode:
                self.negotiated = verify_negotiated_mode(
                    self.profile, self._read_back_mode(),
                    self.profile.backend if self._is_usb_live() else "ffmpeg",
                )
                if self.negotiated.mismatch:
                    self.capture_state = "mode-mismatch"
                    logger.warning(
                        "Capture mode negotiation mismatch for %s: %s mismatched=%s",
                        self.profile.camera_id,
                        self.negotiated.describe(),
                        ",".join(self.negotiated.mismatched_fields),
                    )
                else:
                    self.capture_state = "ok"
                    logger.info(
                        "Capture mode negotiated for %s: %s backend=%s",
                        self.profile.camera_id, self.negotiated.describe(), self.negotiated.backend,
                    )
            self._reconnect_attempt = 0
            return True
        return False

    # -- reading ---------------------------------------------------------------
    def _fingerprint(self, frame: np.ndarray) -> bytes:
        """Cheap duplicate detector: hash of a strided subsample (~1/256 of pixels)."""
        sample = frame[::16, ::16]
        return sample.tobytes()

    def read_frame(self) -> tuple[bool, Optional[np.ndarray]]:
        """Read one frame (freshness: _drain_to_latest on live network sources)."""
        if self.cap is None or not self.cap.isOpened():
            return False, None

        started = self._clock()
        if self._is_live() and self.profile.drain_to_latest:
            ok, frame = self._drain_to_latest(
                max_drain=self.profile.max_drain,
                budget_s=self.profile.drain_budget_s,
            )
        elif self._is_live():
            ok, frame = self.cap.read()
        else:
            ok, frame = self.cap.read()
            if ok:
                self.last_media_index = self.next_media_index
                self.next_media_index += 1
            if ok and self.file_skip_frames > 0:
                for _ in range(self.file_skip_frames):
                    skip_ret, _ = self.cap.read()
                    if not skip_ret:
                        break
                    self.next_media_index += 1
        finished = self._clock()

        if ok and frame is not None:
            self.stats.frame_read_ms.append((finished - started) * 1000.0)
            if self._last_read_stamp is not None:
                self.stats.read_gaps_ms.append((finished - self._last_read_stamp) * 1000.0)
            self._last_read_stamp = finished
            self.stats.frames_read += 1
            fingerprint = self._fingerprint(frame)
            if fingerprint == self._prev_fingerprint:
                self.stats.duplicate_frames += 1
            self._prev_fingerprint = fingerprint
        return ok, frame

    def _drain_to_latest(self, max_drain: int = 30, budget_s: Optional[float] = None) -> tuple[bool, Optional[np.ndarray]]:
        """Grab-drain-retrieve: return only the freshest frame (latest-frame-wins).

        grab() may block until the next frame when the driver queue is empty.
        The time budget is checked AFTER each grab, so a blocking grab costs at
        most one frame period (same as a plain read) while a backed-up queue is
        drained within the budget.
        """
        if self.cap is None:
            return False, None
        started = time.perf_counter()
        got = False
        grabs = 0
        for _ in range(max_drain):
            ret = self.cap.grab()
            if not ret:
                # EOS/empty probe after successful grabs must NOT discard the
                # freshest frame already grabbed (regression: the original
                # dead-code helper threw it away here).
                break
            got = True
            grabs += 1
            if budget_s is not None and (time.perf_counter() - started) >= budget_s:
                break
        if not got:
            return False, None
        ret, frame = self.cap.retrieve()
        self._last_drain_grabs = grabs
        return ret, frame

    # -- legacy helpers (kept for compatibility) --------------------------------
    def push_frame(self, frame: np.ndarray) -> bool:
        """Push frame to queue. Drops oldest if queue full (legacy deque helper)."""
        if len(self.queue) >= self.max_queue_size:
            try:
                self.queue.popleft()
            except IndexError:
                pass
        self.queue.append(frame)
        entry = make_evidence_frame(
            frame, None, self.profile.ring.format, self._clock(), self.frame_count,
            jpeg_quality=self.profile.ring.jpeg_quality,
        )
        self.ring_buffer.append(entry)
        self.frame_count += 1
        return True

    # -- reconnect --------------------------------------------------------------
    def reconnect(self) -> bool:
        """Reconnect with exponential backoff + jitter (1,2,4,...,30s cap)."""
        self.capture_state = "interrupted"
        if self.cap:
            self.cap.release()
            self.cap = None
        self._reconnect_attempt += 1
        delay = next_backoff_delay(self._reconnect_attempt, self.profile.reconnect)
        logger.info(
            "Capture reconnect for %s: attempt=%d backoff=%.2fs",
            self.profile.camera_id, self._reconnect_attempt, delay,
        )
        if self.stop_event.wait(delay):
            return False
        self.capture_state = "reconnecting"
        ok = self.open()
        if ok:
            self.stats.reconnects += 1
            self._reconnect_attempt = 0
        else:
            self.capture_state = "interrupted"
        return ok

    # -- lifecycle / surface -----------------------------------------------------
    def reset_media_timeline(self):
        """Restart the media clock at a prerecorded-media loop boundary."""
        self.next_media_index = 0
        self.last_media_index = 0

    def release(self):
        """Release the capture device."""
        if self.cap:
            self.cap.release()
            self.cap = None

    def get_props(self) -> dict:
        """Return current capture properties (additive keys only)."""
        return {
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "frame_count": self.frame_count,
            "source": str(self.source),
            "captureState": self.capture_state,
            "clockBase": get_capture_clock_base(),
        }

    def health_details(self) -> dict:
        """Additive F-38 detail block (flows through state.set_camera_health)."""
        details = {
            "captureState": self.capture_state,
            "clockBase": get_capture_clock_base(),
            "ringFormat": self.profile.ring.format,
            "drainToLatest": bool(self.profile.drain_to_latest and self._is_network_live()),
        }
        if self.negotiated is not None:
            details.update(self.negotiated.to_dict())
        details.update(self.stats.snapshot())
        return details
