"""Async incident capture queue + pre-event ring sweep (S-04 / WT-22).

Design constraints this module enforces:

* **The alert path never does capture work.** ``trigger()`` snapshots the ring
  and enqueues a job; all scoring, crop-reference building, record writing and
  (later) face/enhancement handoff happen on the worker thread. ``trigger()``
  is O(ring entries) reference copying and cannot block on the worker.
* **Bounded and lossy by design, with telemetry.** Both the job queue and each
  job's post-window collection are bounded and drop OLDEST entries; every drop
  is counted (``dropped_jobs`` / ``dropped_frames``) so silent loss is
  impossible.
* **Pre-event ring sweep T-10s..T+5s.** The clearest frame usually precedes the
  trigger, so the ring keeps ``pre_seconds`` of sampled frames before the alert
  and each job keeps collecting until ``alert_time + post_seconds``.
* **Capture pending is a first-class state** (contract for the incident view):
  ``status()['state'] == 'pending'`` while any job is outstanding.

Determinism: selection itself is deterministic (see ``best_frame``); the queue
adds no randomness. Wall-clock behaviour is honest about being asynchronous.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np

import best_frame
from frame_reference import CropRef, FrameRef, hash_array_raw

BEST_FRAME_RECORD_SCHEMA = "sentinel.best_frame_record/v1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RingEntry:
    captured_at: float
    frame: np.ndarray
    frame_sequence: Optional[int] = None
    sample_timestamp: Optional[float] = None
    iso_time: Optional[str] = None
    native_frame: Optional[np.ndarray] = None
    frame_sha256: Optional[str] = None
    hash_format: Optional[str] = None
    native_frame_sha256: Optional[str] = None
    native_hash_format: Optional[str] = None
    sequence_is_synthetic: bool = False

    def ensure_hash(self) -> tuple[str, str]:
        """Hash the exact sampled pixels scored and described by FrameRef."""
        if self.frame_sha256 is None or self.hash_format is None:
            digest, fmt = hash_array_raw(self.frame)
            self.frame_sha256, self.hash_format = digest, fmt
        return self.frame_sha256, self.hash_format

    def ensure_native_hash(self) -> Optional[tuple[str, str]]:
        """Hash the associated source-resolution capture as a separate asset."""
        if self.native_frame is None:
            return None
        if self.native_frame_sha256 is None or self.native_hash_format is None:
            digest, fmt = hash_array_raw(self.native_frame)
            self.native_frame_sha256, self.native_hash_format = digest, fmt
        return self.native_frame_sha256, self.native_hash_format


class PreEventRing:
    """Bounded ring of sampled frames for the pre/post incident window."""

    def __init__(self, max_seconds: float = 10.0, sample_fps: float = 4.0,
                 native_fps: float = 1.0, native_max_frames: int = 24):
        if max_seconds <= 0:
            raise ValueError("max_seconds must be > 0")
        if sample_fps <= 0:
            raise ValueError("sample_fps must be > 0")
        self.max_seconds = float(max_seconds)
        self.sample_interval = 1.0 / float(sample_fps)
        self.native_interval = (1.0 / float(native_fps)) if native_fps and native_fps > 0 else None
        self.native_max_frames = max(0, int(native_max_frames))
        self._entries: list[RingEntry] = []
        self._lock = threading.Lock()
        self._last_sample: Optional[float] = None
        self._last_native: Optional[float] = None
        self._last_captured_at: Optional[float] = None
        self._synthetic_sequence = 0
        self.dropped_samples = 0

    def last_captured_at(self) -> Optional[float]:
        """Latest fed timestamp (capture clock) — the authoritative 'now'."""
        return self._last_captured_at

    def add(self, captured_at: float, frame: np.ndarray, frame_sequence: Optional[int] = None,
            sample_timestamp: Optional[float] = None,
            native_frame: Optional[np.ndarray] = None) -> Optional[RingEntry]:
        """Store a frame if the sampling cadence allows.

        Returns the stored entry for sampled frames (``None`` otherwise) so the
        caller can fan the entry out to active jobs without re-scanning the
        ring. No frame copy happens when the cadence skips the frame.
        """
        captured_at = float(captured_at)
        self._last_captured_at = captured_at
        sampled = self._last_sample is None or (captured_at - self._last_sample) >= self.sample_interval
        native_due = (native_frame is not None and self.native_interval is not None
                      and (self._last_native is None or (captured_at - self._last_native) >= self.native_interval))
        if not sampled and not native_due:
            return None
        with self._lock:
            entry: Optional[RingEntry] = None
            if sampled:
                synthetic = frame_sequence is None
                if synthetic:
                    self._synthetic_sequence += 1
                entry = RingEntry(
                    captured_at=captured_at,
                    frame=np.array(frame, copy=True),
                    frame_sequence=int(self._synthetic_sequence if synthetic else frame_sequence),
                    sample_timestamp=sample_timestamp,
                    iso_time=_utc_now_iso(),
                    sequence_is_synthetic=synthetic,
                )
                self._entries.append(entry)
                self._last_sample = captured_at
            if native_due and self._entries and self.native_max_frames > 0:
                stored = sum(1 for item in self._entries if item.native_frame is not None)
                target = self._entries[-1]
                if target.native_frame is None and stored < self.native_max_frames:
                    target.native_frame = np.array(native_frame, copy=True)
                    self._last_native = captured_at
            self._prune(captured_at)
            return entry

    def _prune(self, now: float) -> None:
        cutoff = now - self.max_seconds
        while self._entries and self._entries[0].captured_at < cutoff:
            self._entries.pop(0)

    def snapshot(self, start: float, end: float) -> list[RingEntry]:
        with self._lock:
            return [entry for entry in self._entries if start <= entry.captured_at <= end]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._last_sample = None
            self._last_native = None
            self._last_captured_at = None

    def stats(self) -> dict[str, Any]:
        with self._lock:
            native = sum(1 for entry in self._entries if entry.native_frame is not None)
            return {"entries": len(self._entries), "native_entries": native,
                    "window_seconds": self.max_seconds, "sample_interval": self.sample_interval}


@dataclass
class CaptureJob:
    alert_id: str
    alert_time: float
    pre_entries: list[RingEntry]
    deadline: float
    created_at: float
    camera_id: str = ""
    post_entries: list[RingEntry] = field(default_factory=list)
    state: str = "pending"
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    dropped_post_frames: int = 0
    trigger_thread: str = ""
    finalized_capture_at: Optional[float] = None
    truncation_reason: Optional[str] = None
    force_finalize: bool = False


class IncidentCapture:
    """Bounded drop-oldest capture queue with a single selection worker."""

    def __init__(self,
                 ring: Optional[PreEventRing] = None,
                 queue_capacity: int = 8,
                 pre_seconds: float = 10.0,
                 post_seconds: float = 5.0,
                 max_post_frames_per_job: int = 64,
                 camera_id: str = "",
                 record_dir: Optional[str | Path] = None,
                 on_complete: Optional[Callable[[dict[str, Any]], None]] = None,
                 clock: Callable[[], float] = time.monotonic,
                 config: Optional[best_frame.BestFrameConfig] = None,
                 start_worker: bool = True):
        self.ring = ring if ring is not None else PreEventRing(max_seconds=max(pre_seconds, 10.0))
        self.queue_capacity = max(1, int(queue_capacity))
        self.pre_seconds = float(pre_seconds)
        self.post_seconds = float(post_seconds)
        self.max_post_frames_per_job = max(1, int(max_post_frames_per_job))
        self.camera_id = str(camera_id or "")
        self.record_dir = Path(record_dir) if record_dir is not None else None
        self.on_complete = on_complete
        self._clock = clock
        self.config = config or best_frame.load_config()
        self._jobs: list[CaptureJob] = []
        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._stop = threading.Event()
        self.counter = {"triggered": 0, "completed": 0, "failed": 0,
                        "dropped_jobs": 0, "dropped_frames": 0}
        self._last_result: Optional[dict[str, Any]] = None
        self._worker: Optional[threading.Thread] = None
        if start_worker:
            self._worker = threading.Thread(target=self._run, name=f"capture-{self.camera_id or 'cam'}",
                                            daemon=True)
            self._worker.start()

    # -- capture loop side (never blocks, never scores) -------------------
    def feed(self, captured_at: float, frame: np.ndarray, frame_sequence: Optional[int] = None,
             sample_timestamp: Optional[float] = None, native_frame: Optional[np.ndarray] = None) -> bool:
        with self._lock:
            entry = self.ring.add(captured_at, frame, frame_sequence, sample_timestamp, native_frame)
            if entry is None:
                return False
            for job in self._jobs:
                if job.state != "pending" or job.force_finalize:
                    continue
                if not (job.alert_time <= captured_at <= job.deadline):
                    continue
                job.post_entries.append(entry)
                while len(job.post_entries) > self.max_post_frames_per_job:
                    job.post_entries.pop(0)
                    job.dropped_post_frames += 1
                    self.counter["dropped_frames"] += 1
        return True

    # -- alert path side ---------------------------------------------------
    def trigger(self, alert_id: str, alert_time: Optional[float] = None,
                camera_id: Optional[str] = None) -> dict[str, Any]:
        """Enqueue a capture job for ``alert_id``. O(1) + bounded ring snapshot.

        ``alert_time`` MUST be on the same clock base as the timestamps passed to
        ``feed`` (the capture clock). When omitted, the newest fed capture
        timestamp is used; ``time.monotonic()`` is only the last-resort fallback
        for a ring that has never been fed, so no diff ever mixes clock bases.
        """
        with self._wake:
            if alert_time is None:
                alert_time = self.ring.last_captured_at()
            if alert_time is None:
                alert_time = self._clock()
            alert_time = float(alert_time)
            job = CaptureJob(
                alert_id=str(alert_id),
                alert_time=alert_time,
                pre_entries=self.ring.snapshot(alert_time - self.pre_seconds, alert_time),
                deadline=alert_time + self.post_seconds,
                # Worker readiness is measured with the internal monotonic clock
                # (relative elapsed), never by comparing bases.
                created_at=self._clock(),
                camera_id=str(camera_id if camera_id is not None else self.camera_id),
                trigger_thread=threading.current_thread().name,
            )
            self._jobs.append(job)
            while len(self._jobs) > self.queue_capacity:
                dropped = self._jobs.pop(0)
                dropped.state = "dropped"
                self.counter["dropped_jobs"] += 1
            self.counter["triggered"] += 1
            self._wake.notify_all()
        return self._job_status(job)

    def status(self) -> dict[str, Any]:
        with self._lock:
            pending = sum(1 for job in self._jobs if job.state in {"pending", "finalizing"})
            ready = sum(1 for job in self._jobs if job.state == "ready")
            failed = sum(1 for job in self._jobs if job.state == "failed")
            dropped = sum(1 for job in self._jobs if job.state == "dropped")
            status = {
                "state": "pending" if pending else "idle",
                "pending": pending,
                "ready": ready,
                "failed": failed,
                "dropped_jobs_in_window": dropped,
                "queue_capacity": self.queue_capacity,
                **self.counter,
                "ring": self.ring.stats(),
            }
            if self._last_result is not None:
                status["last_selection"] = {
                    "alert_id": self._last_result.get("alert_id"),
                    "best_frame_id": (self._last_result.get("best") or {}).get("frame_id"),
                    "candidates": (self._last_result.get("window") or {}).get("candidates"),
                    "capture_status": self._last_result.get("capture_status"),
                }
            return status

    def end_epoch(self, reason: str = "capture-epoch-ended") -> int:
        """Close pending incidents honestly before a source timeline resets.

        Pending jobs keep their captured frame references and are finalized by
        the normal worker as partial records when the post-window endpoint was
        not observed. Clearing the ring prevents pre-event frames from the old
        source epoch from entering later incidents.
        """
        truncation_reason = str(reason or "capture-epoch-ended")
        forced = 0
        with self._wake:
            latest_capture = self.ring.last_captured_at()
            for job in self._jobs:
                if job.state != "pending":
                    continue
                job.finalized_capture_at = latest_capture
                job.truncation_reason = truncation_reason
                job.force_finalize = True
                forced += 1
            self.ring.clear()
            self._wake.notify_all()
        return forced

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        with self._wake:
            self._wake.notify_all()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=timeout)

    def wait_for_idle(self, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if not any(job.state in {"pending", "finalizing"} for job in self._jobs):
                    return True
            self._stop.wait(0.01)
        return False

    # -- worker ------------------------------------------------------------
    def _job_status(self, job: CaptureJob) -> dict[str, Any]:
        return {"alert_id": job.alert_id, "state": job.state,
                "pre_candidates": len(job.pre_entries), "deadline": job.deadline}

    def _run(self) -> None:
        while not self._stop.is_set():
            job = None
            with self._wake:
                pending = [entry for entry in self._jobs if entry.state == "pending"]
                if pending:
                    due = self._clock() - pending[0].created_at
                    if pending[0].force_finalize or due >= self.post_seconds:
                        job = pending[0]
                        if job.finalized_capture_at is None:
                            job.finalized_capture_at = self.ring.last_captured_at()
                        job.state = "finalizing"
                    else:
                        self._wake.wait(min(0.05, max(0.0, self.post_seconds - due)))
                else:
                    self._wake.wait(0.05)
            if job is None:
                continue
            try:
                record = self._build_record(job)
                job.result = record
                job.state = "ready"
                with self._lock:
                    self.counter["completed"] += 1
                    self._last_result = record
                if self.on_complete is not None:
                    try:
                        self.on_complete(record)
                    except Exception:  # callback failures never kill the worker
                        pass
            except Exception as exc:  # a failed selection is reported, never swallowed
                job.state = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                with self._lock:
                    self.counter["failed"] += 1

    def _candidates(self, job: CaptureJob) -> list[dict[str, Any]]:
        entries = list(job.pre_entries) + list(job.post_entries)
        candidates: list[dict[str, Any]] = []
        for entry in entries:
            frame_digest, hash_format = entry.ensure_hash()
            frame_ref = FrameRef(
                camera_id=job.camera_id or self.camera_id or "unscoped",
                frame_sequence=int(entry.frame_sequence),
                captured_at=float(entry.captured_at),
                iso_time=str(entry.iso_time or _utc_now_iso()),
                width=int(entry.frame.shape[1]),
                height=int(entry.frame.shape[0]),
                frame_sha256=frame_digest,
                hash_format=hash_format,
                sample_timestamp=entry.sample_timestamp,
                source_width=(int(entry.native_frame.shape[1]) if entry.native_frame is not None else None),
                source_height=(int(entry.native_frame.shape[0]) if entry.native_frame is not None else None),
                bbox_space="model_input",
            ).to_dict()
            candidates.append({"frame": entry.frame, "frame_ref": frame_ref, "entry": entry})
        return candidates

    def _build_record(self, job: CaptureJob) -> dict[str, Any]:
        candidates = self._candidates(job)
        best = best_frame.select_best(candidates, self.config)
        now = self._clock()
        latest_capture = (job.finalized_capture_at if job.finalized_capture_at is not None
                          else self.ring.last_captured_at())
        post_window_endpoint_reached = latest_capture is not None and latest_capture >= job.deadline
        last_post_candidate_at = max((entry.captured_at for entry in job.post_entries), default=None)
        record: dict[str, Any] = {
            "schema": BEST_FRAME_RECORD_SCHEMA,
            "capture_status": "complete" if post_window_endpoint_reached else "partial",
            "alert_id": job.alert_id,
            "camera_id": job.camera_id or self.camera_id,
            "alert_time": {"monotonic": job.alert_time, "iso_time": _utc_now_iso()},
            "finalized_at": {"monotonic": now, "iso_time": _utc_now_iso()},
            "window": {
                "pre_seconds": self.pre_seconds,
                "post_seconds": self.post_seconds,
                "candidates": len(candidates),
                "pre_candidates": len(job.pre_entries),
                "post_candidates": len(job.post_entries),
                "dropped_post_frames": job.dropped_post_frames,
                "sample_interval_seconds": self.ring.sample_interval,
                "post_window_status": "complete" if post_window_endpoint_reached else "truncated",
                "post_window_truncated": not post_window_endpoint_reached,
                "post_window_truncation_reason": (None if post_window_endpoint_reached
                                                   else (job.truncation_reason or "capture-ended-before-post-deadline")),
                "post_window_endpoint_reached": post_window_endpoint_reached,
                "post_window_deadline": job.deadline,
                "last_capture_at": latest_capture,
                "last_post_candidate_at": last_post_candidate_at,
                "frame_sequences_synthetic": any(entry.sequence_is_synthetic for entry in
                                                 list(job.pre_entries) + list(job.post_entries)),
            },
            "scoring": {"config_source": self.config.source,
                        "scoring_thread": threading.current_thread().name,
                        "trigger_thread": job.trigger_thread},
            "policy": {"identity_recognition": False, "derivative": False,
                       "note": "camera-observed frames only; no identity claim is made"},
        }
        if best is None:
            record["best"] = None
            record["reason"] = "no captured frames in window"
            return record
        reference = best["frame_ref"]
        entry: RingEntry = best["entry"]
        native_hash = entry.ensure_native_hash()
        record["best"] = {
            "frame_id": reference["frame_id"],
            "camera_id": reference["camera_id"],
            "frame_sequence": reference["frame_sequence"],
            "captured_at": reference["captured_at"],
            "sample_timestamp": reference["sample_timestamp"],
            "iso_time": reference["iso_time"],
            "frame_sha256": reference["frame_sha256"],
            "hash_format": reference["hash_format"],
            "width": reference["width"],
            "height": reference["height"],
            "native_available": entry.native_frame is not None,
            "native_shape": list(entry.native_frame.shape) if entry.native_frame is not None else None,
            "native_frame": (None if native_hash is None else {
                "sha256": native_hash[0],
                "hash_format": native_hash[1],
                "width": int(entry.native_frame.shape[1]),
                "height": int(entry.native_frame.shape[0]),
            }),
        }
        record["score_vector"] = best["score"]
        record["ranked"] = best["ranked"]
        record["candidate_count"] = best["candidate_count"]
        # SC-8 parent references for every candidate frame that contributed.
        record["parents"] = [
            {
                "frame_id": candidate["frame_ref"]["frame_id"],
                "frame_sha256": candidate["frame_ref"]["frame_sha256"],
                "hash_format": candidate["frame_ref"]["hash_format"],
                "captured_at": candidate["frame_ref"]["captured_at"],
                "sample_timestamp": candidate["frame_ref"]["sample_timestamp"],
            }
            for candidate in candidates
        ]
        record["crop_refs"] = self._crop_refs(job, reference, record["score_vector"])
        if self.record_dir is not None:
            record["record_path"] = self._write_record(job.alert_id, record)
        return record

    def _crop_refs(self, job: CaptureJob, reference: dict[str, Any], score: dict[str, Any]) -> list[dict[str, Any]]:
        """Build CropRefs for the scored subjects of the best frame (WT-21/WT-23 contract)."""
        refs: list[dict[str, Any]] = []
        camera = reference["camera_id"]
        sequence = int(reference["frame_sequence"])
        for face in score.get("faces", []):
            bbox = None
            for key in ("bbox_xyxy_source", "bbox_xyxy"):
                if face.get(key):
                    bbox = tuple(int(round(float(value))) for value in face[key])
                    break
            if bbox is None:
                continue
            track_ref = face.get("track_ref")
            refs.append(CropRef(
                camera_id=camera,
                frame_sequence=sequence,
                captured_at=float(reference["captured_at"]),
                iso_time=str(reference["iso_time"]),
                subject_kind="face",
                bbox_xyxy=(bbox[0], bbox[1], max(bbox[0] + 1, bbox[2]), max(bbox[1] + 1, bbox[3])),
                bbox_space="model_input",
                source_frame_sha256=str(reference["frame_sha256"]),
                hash_format=str(reference["hash_format"]),
                alert_id=job.alert_id,
                sample_timestamp=reference["sample_timestamp"],
                track_ref=str(track_ref) if track_ref else None,
                face_index=int(face.get("face_index", len(refs))),
                is_derivative=False,
            ).to_dict())
        return refs

    def _write_record(self, alert_id: str, record: dict[str, Any]) -> str:
        directory = Path(self.record_dir)  # type: ignore[arg-type]
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{alert_id}.json"
        temp = path.with_suffix(".json.part")
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
        return str(path)
