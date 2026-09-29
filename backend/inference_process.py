"""Inference subprocess — loads all AI models in a separate process.

Runs violence detection, weapon detection, person detection, and motion
estimation in a dedicated process that owns its own CUDA context. This
bypasses the Python GIL and prevents AI inference from blocking the
capture/render pipeline.

Communication:
  - Receives numpy frames via multiprocessing.Queue (frame_queue)
  - Pushes result dicts via multiprocessing.Queue (result_queue)
  - Stops via multiprocessing.Event (stop_event)
"""
from __future__ import annotations

import time
import multiprocessing as mp
import uuid
from collections import deque
from queue import Empty
from typing import Optional

import cv2
import numpy as np


MOTION_GATE_THRESHOLD = 0.0
MOTION_SIZE = (64, 64)
MODALITY_STALE_AFTER_SECONDS = 5.0

# Consumer-side frame queue policy (measured in EXP-15.02; see docs/campaign/
# experiments/15-02-queue-policy.md). "drop-newest" preserves the historical
# producer-side backpressure behaviour; "latest-wins" drains stale queued
# packets at the consumer so decisions run on the freshest frame.
QUEUE_POLICIES = ("drop-newest", "latest-wins")


def _queue_depth(channel) -> Optional[int]:
    """Instantaneous queue depth; None when the abstraction lacks qsize."""
    getter = getattr(channel, "qsize", None)
    if getter is None:
        return None
    try:
        return int(getter())
    except Exception:
        return None


def _note_frame_received(telemetry: dict, packet) -> None:
    """Account producer-side drops as gaps in the capture-loop sequence.

    Every dequeued packet (including ones later discarded by a queue policy
    or by a media-reset drain) must be noted here so a discard is never
    miscounted as a producer drop. R-2 is measured twice: this derived
    counter and the producer-side ``frameQueueDropped`` counter must agree.
    """
    seq = getattr(packet, "sequence", None)
    if seq is None:
        return
    try:
        seq = int(seq)
    except (TypeError, ValueError):
        return
    last = telemetry["last_sequence"]
    if seq > last:
        telemetry["frame_queue_dropped_derived"] += seq - last - 1
        telemetry["last_sequence"] = seq
    # seq <= last: capture-loop counter restart; never subtract.


def default_result() -> dict:
    """Return a default empty result dict."""
    return {
        "is_threat": False,
        "threat_confidence": 0.0,
        "violence_conf": 0.0,
        "weapon_score": 0.0,
        "weapon_labels": [],
        "weapon_bbox": None,
        "violence_bbox": None,
        "person_count": 0,
        "tracks": [],
        "visible_person_count": 0,
        "active_track_count": 0,
        "unique_person_estimate_window": None,
        "track_failure_flags": {},
        "person_tracker": "",
        "motion_score": 0.0,
        "fps": 0.0,
        "video_width": 0,
        "video_height": 0,
        "frame_idx": 0,
        "timestamp": 0.0,
        "violence_capture_timestamp": 0.0,
    }


def _motion_thumbnail(frame: np.ndarray) -> Optional[np.ndarray]:
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, MOTION_SIZE, interpolation=cv2.INTER_AREA)
    except Exception:
        return None


def _score_motion_thumbnails(
    previous_small: Optional[np.ndarray],
    current_small: Optional[np.ndarray],
) -> float:
    if previous_small is None or current_small is None:
        return 0.0
    try:
        diff = cv2.absdiff(previous_small, current_small)
        return float(diff.mean() / 255.0)
    except Exception:
        return 0.0


def estimate_motion_score(
    previous_frame: Optional[np.ndarray],
    current_frame: np.ndarray,
) -> float:
    if previous_frame is None:
        return 0.0
    return _score_motion_thumbnails(
        _motion_thumbnail(previous_frame),
        _motion_thumbnail(current_frame),
    )


def _normalize_bbox(raw_bbox) -> Optional[list[float]]:
    if raw_bbox and isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
        try:
            return [float(v) for v in raw_bbox]
        except (TypeError, ValueError):
            return None
    return None


def _select_fresh_observation_score(*, fresh_violence: bool, violence: Optional[dict],
                                    fresh_weapon: bool, weapon: Optional[dict]) -> Optional[dict]:
    """Select a decision score from newly completed modality observations only.

    Cached scores remain useful for overlays and health, but must never become
    another vote merely because the other model completed a new observation.
    """
    candidates = []
    if fresh_violence and violence is not None:
        candidates.append(violence)
    if fresh_weapon and weapon is not None:
        candidates.append(weapon)
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: float(candidate["score"]))


def read_weapon_signal(weapon_engine, frame: np.ndarray) -> tuple[float, list[str], Optional[list[float]]]:
    """Read the latest weapon signal without zeroing it between inference ticks."""
    if weapon_engine is None:
        return 0.0, [], None

    signal = None
    try:
        signal = weapon_engine.process_frame(frame)
    except Exception:
        signal = None

    if not signal:
        try:
            signal = weapon_engine.latest_signal()
        except Exception:
            signal = None

    if not signal:
        return 0.0, [], None

    return (
        float(signal.get("score", 0.0)),
        list(signal.get("labels", [])),
        _normalize_bbox(signal.get("bbox")),
    )


def read_violence_signal(violence_pipeline, frame: np.ndarray) -> tuple[float, int]:
    """Trigger violence inference and return the latest completed async result."""
    if violence_pipeline is None or not getattr(violence_pipeline, "enabled", False):
        return 0.0, 0

    try:
        violence_pipeline.process_frame(frame)
    except Exception:
        return 0.0, 0

    state_lock = getattr(violence_pipeline, "_state_lock", None)
    if state_lock is None:
        return (
            float(getattr(violence_pipeline, "_last_conf", 0.0)),
            int(getattr(violence_pipeline, "_last_label", 0)),
        )

    with state_lock:
        return (
            float(getattr(violence_pipeline, "_last_conf", 0.0)),
            int(getattr(violence_pipeline, "_last_label", 0)),
        )


def _scale_person_tracks(tracks, input_size, source_size):
    """Copy inference-pixel tracks into original source-pixel coordinates."""
    input_width, input_height = input_size
    source_width, source_height = source_size
    if min(input_width, input_height, source_width, source_height) <= 0:
        raise ValueError("Invalid person coordinate dimensions")
    scaled = []
    for track in tracks or []:
        if not isinstance(track, dict):
            continue
        try:
            box = np.asarray(track.get('bbox'), dtype=np.float64)
        except (ValueError, TypeError):
            continue
        if box.shape != (4,) or not np.isfinite(box).all():
            continue
        box = box.copy()
        box[[0, 2]] = np.clip(box[[0, 2]] * source_width / input_width, 0, source_width)
        box[[1, 3]] = np.clip(box[[1, 3]] * source_height / input_height, 0, source_height)
        if box[2] > box[0] and box[3] > box[1]:
            scaled.append({**track, 'bbox': box.tolist()})
    return scaled


def inference_worker(frame_queue, result_queue, stop_event, config):
    """Own models in one process; publish only genuinely completed observations."""
    t_entry = time.monotonic()
    import logging
    import os
    import sys
    from concurrent.futures import ThreadPoolExecutor
    from queue import Full
    import torch
    cv2.setNumThreads(1)
    torch.set_num_threads(2)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass  # In-process tests may already have initialized PyTorch's shared pool.
    from decision_config import DecisionConfig, load_decision_config
    from temporal_frames import FramePacket
    log=logging.getLogger(__name__)
    # --- worker identity + monotone telemetry (SC-7 / WT-13 export) ---------
    process_run_id = uuid.uuid4().hex
    worker_pid = os.getpid()
    telemetry = {
        "last_sequence": 0,
        "frame_queue_dropped_derived": 0,
        "frame_queue_discarded_by_policy": 0,
        "frame_queue_discarded_at_reset": 0,
        "result_queue_dropped": 0,
        "violence_completed": 0,
        "weapon_completed": 0,
        "person_completed": 0,
        "startup_model_load_ms": None,
        "startup_first_frame_ms": None,
        "startup_first_result_ms": None,
        "startup_first_observation_ms": None,
    }
    # Capture clock base declared by the producer (SC-6): timestamps crossing
    # the process boundary are only ever diffed within one base. Durations not
    # involving producer stamps are measured on the QPC clock (perf_counter).
    capture_clock_base = str(config.get("capture_clock_base", "monotonic-gettickcount64"))
    if capture_clock_base == "perf-qpc":
        def _capture_now():
            return time.perf_counter()
    else:
        capture_clock_base = "monotonic-gettickcount64"
        def _capture_now():
            return time.monotonic()
    requested_policy = str(
        config.get("queue_policy") or os.environ.get("AI_SENTINEL_QUEUE_POLICY", "drop-newest")
    ).strip().lower()
    queue_policy = requested_policy if requested_policy in QUEUE_POLICIES else "drop-newest"
    last_put_ms = None  # serialization cost of the previous result put; rides the next result
    device_name=config.get('device','cuda')
    device=torch.device(device_name if torch.cuda.is_available() and str(device_name).startswith('cuda') else 'cpu')
    policy=DecisionConfig.from_mapping(config['decision_config']) if config.get('decision_config') else load_decision_config()
    health={}
    def mark(name,status,reason=''):
        health[name]={'status':status,'reason':reason}
    violence_pipeline=None
    weapon_engine=None
    person_detector=None
    try:
        from inference import ViolenceInferencePipeline
        violence_pipeline=ViolenceInferencePipeline(config.get('weights_path','best_model.pt'),device,threshold=policy.violence_threshold,stride=config.get('violence_stride',16))
        mark('violence','OK' if violence_pipeline.enabled else 'FAILED',getattr(violence_pipeline,'disabled_reason',''))
    except Exception as exc:
        log.exception('Violence model initialization failed')
        mark('violence','FAILED',type(exc).__name__)
    try:
        from weapon import WeaponSignalEngine, WeaponConfig
        weapon_engine=WeaponSignalEngine(WeaponConfig.from_settings(config.get('weapon_config',{}),os.environ),device=device)
        if weapon_engine.enabled:weapon_engine.preload()
        status=weapon_engine.status()
        mark('weapon','FAILED' if status.get('failed') else 'OK' if status.get('ready') else 'DISABLED' if not weapon_engine.enabled else 'FAILED',status.get('reason',''))
    except Exception as exc:
        log.exception('Weapon model initialization failed')
        mark('weapon','FAILED',type(exc).__name__)
    if config.get('person_overlay_enabled',True):
        try:
            from person_detector import PersonDetector
            person_detector=PersonDetector(conf_threshold=config.get('person_conf_threshold',.45),device=device.type,camera_id=str(config.get('camera_id','') or ''))
            mark('person','OK' if person_detector.enabled else 'FAILED')
        except Exception as exc:
            log.exception('Person model initialization failed')
            mark('person','FAILED',type(exc).__name__)
    else:mark('person','DISABLED','Disabled by configuration')
    from pathlib import Path
    try:
        from calibration_utils import calibration_state as resolve_calibration_state
        calibration_state=resolve_calibration_state(
            base_dir=Path(__file__).resolve().parent,
            model_path=config.get('weights_path'),
            use_cache=True,
        )
    except Exception:
        calibration_state={"status":"unverified","calibrated":False}
    violence_calibration_status=str(calibration_state.get('status','unverified'))
    violence_calibration_active=bool(calibration_state.get('calibrated'))
    mark('calibration','OK' if violence_calibration_active else 'DEGRADED',
         f"Violence score calibration status: {violence_calibration_status}")
    executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='person')
    person_future=None
    person_future_sizes=None
    tracks=[]
    frame_idx=0
    previous_motion=None
    previous_versions=(0,0)
    sequence=0
    observation_score=0.0
    observation_score_source="unknown"
    observation_raw_model_score=None
    observation_calibrated_probability=None
    observation_calibration_status="unverified"
    sample_time=0.0
    latest_violence=0.0
    violence_observation_score=0.0
    violence_raw_model_score=None
    violence_calibrated_probability=None
    violence_id=0
    violence_completed_at=0.0
    violence_capture_timestamp=0.0
    weapon_raw_model_score=None
    weapon_calibrated_probability=None
    weapon_calibration_status="unverified"
    runtime_generation=int(config.get('inference_generation',0))
    ready_event=config.get('ready_event')
    reset_event=config.get('reset_event')
    reset_ack=config.get('reset_ack')

    # Signal that model construction is complete before accepting a reset
    # request.  The parent may loop a short prerecorded source during startup.
    telemetry["startup_model_load_ms"] = (time.monotonic() - t_entry) * 1000.0
    if queue_policy != requested_policy:
        mark("delivery", "DEGRADED", f"Unknown queue policy {requested_policy!r}; using drop-newest")
    if ready_event is not None:
        ready_event.set()

    def reset_runtime_state():
        """Reset model/window state without reloading weights at media EOF."""
        nonlocal person_future, person_future_sizes, tracks, frame_idx, previous_motion
        nonlocal previous_versions, sequence, observation_score, observation_score_source
        nonlocal observation_raw_model_score, observation_calibrated_probability, observation_calibration_status
        nonlocal sample_time
        nonlocal latest_violence, violence_observation_score, violence_id, violence_completed_at
        nonlocal violence_raw_model_score, violence_calibrated_probability
        nonlocal violence_capture_timestamp, runtime_generation
        nonlocal weapon_raw_model_score, weapon_calibrated_probability, weapon_calibration_status
        if person_future is not None and not person_future.done():
            person_future.cancel()
        person_future = None
        person_future_sizes = None
        tracks = []
        frame_idx = 0
        previous_motion = None
        previous_versions = (0, 0)
        sequence = 0
        observation_score = 0.0
        observation_score_source = "unknown"
        observation_raw_model_score = None
        observation_calibrated_probability = None
        observation_calibration_status = "unverified"
        sample_time = 0.0
        latest_violence = 0.0
        violence_observation_score = 0.0
        violence_raw_model_score = None
        violence_calibrated_probability = None
        violence_id = 0
        violence_completed_at = 0.0
        violence_capture_timestamp = 0.0
        weapon_raw_model_score = None
        weapon_calibrated_probability = None
        weapon_calibration_status = "unverified"
        runtime_generation += 1
        if violence_pipeline is not None and hasattr(violence_pipeline, 'reset'):
            violence_pipeline.reset()
        if weapon_engine is not None and hasattr(weapon_engine, 'reset'):
            weapon_engine.reset()
        # Parent does not enqueue the next media epoch until this ack arrives.
        # Drain both IPC queues here so tail results cannot be consumed after
        # the parent has reset its decision/render state.
        for channel in (frame_queue, result_queue):
            # The benchmark queue probe intentionally exposes only ``get``;
            # drain its wrapped multiprocessing queue directly so reset does
            # not call the probe with FramePacket (which has no ``nbytes``).
            drain_channel = getattr(channel, 'wrapped', channel)
            getter = getattr(drain_channel, 'get_nowait', None)
            if getter is None:
                continue
            while True:
                try:
                    discarded = getter()
                except Empty:
                    break
                # Note drained packets so a reset discard never masquerades as
                # a producer drop in the R-2 derived counter.
                if getattr(discarded, "sequence", None) is not None:
                    telemetry["frame_queue_discarded_at_reset"] += 1
                    _note_frame_received(telemetry, discarded)
        if reset_event is not None:
            reset_event.clear()
        if reset_ack is not None:
            reset_ack.set()

    def _monotonic_age_seconds(timestamp, now):
        try:
            stamp = float(timestamp)
        except (TypeError, ValueError):
            return None
        if stamp <= 0:
            return None
        return max(0.0, now - stamp)

    try:
        while not stop_event.is_set():
            if reset_event is not None and reset_event.is_set():
                reset_runtime_state()
                continue
            backlog_frames = _queue_depth(frame_queue)
            try:packet=frame_queue.get(timeout=.1)
            except Empty:continue
            t_dequeue = time.monotonic()
            t_dequeue_qpc = time.perf_counter()
            _note_frame_received(telemetry, packet)
            if queue_policy == "latest-wins":
                # Consumer-side latest-wins (EXP-15.02): discard stale queued
                # packets so decisions run on the freshest captured frame.
                drain = getattr(frame_queue, "get_nowait", None)
                if drain is not None:
                    while True:
                        try:newer = drain()
                        except Empty:break
                        telemetry["frame_queue_discarded_by_policy"] += 1
                        _note_frame_received(telemetry, newer)
                        packet = newer
                        t_dequeue = time.monotonic()
                        t_dequeue_qpc = time.perf_counter()
            if reset_event is not None and reset_event.is_set():
                telemetry["frame_queue_discarded_at_reset"] += 1
                reset_runtime_state()
                continue
            t_preprocess = time.perf_counter()
            enqueued_at = getattr(packet, "enqueued_at", None)
            enqueued_at_qpc = getattr(packet, "enqueued_at_qpc", None)
            if telemetry["startup_first_frame_ms"] is None:
                telemetry["startup_first_frame_ms"] = (t_dequeue - t_entry) * 1000.0
            # Queue envelopes can be imported as temporal_frames or backend.temporal_frames.
            # Check the envelope fields, not Python class identity across import aliases.
            if not isinstance(packet, np.ndarray) and isinstance(getattr(packet, 'frame', None), np.ndarray):
                frame=packet.frame
                captured_at=packet.captured_at
                media_timestamp=getattr(packet,'sample_timestamp',None)
                width,height=packet.source_width,packet.source_height
                source_fps=packet.source_fps
                if packet.decision_config:
                    try:policy=DecisionConfig.from_mapping(packet.decision_config)
                    except (TypeError,ValueError):mark('configuration','FAILED','Invalid runtime policy update')
            else:
                frame=packet
                captured_at=_capture_now()
                enqueued_at = None
                enqueued_at_qpc = None
                media_timestamp=None
                width,height=frame.shape[1],frame.shape[0]
                source_fps=config.get('source_fps',30.0)
            window_clock_source='file-media' if media_timestamp is not None else 'monotonic-capture'
            window_timestamp=captured_at if media_timestamp is None else media_timestamp
            frame_idx+=1
            current_motion = _motion_thumbnail(frame)
            motion = _score_motion_thumbnails(previous_motion, current_motion)
            previous_motion = current_motion
            stage_preprocess_ms = (time.perf_counter() - t_preprocess) * 1000.0
            t_inference = time.perf_counter()
            violence_tick_failed=False
            if violence_pipeline is not None and violence_pipeline.enabled:
                violence_pipeline.threshold=policy.violence_threshold
                try:
                    if not np.isfinite(window_timestamp):
                        raise ValueError('Invalid source sample timestamp')
                    process_kwargs = {'captured_at':window_timestamp,'nominal_fps':source_fps}
                    if hasattr(violence_pipeline,'_last_source_capture_at'):
                        process_kwargs['source_captured_at']=captured_at
                    violence_pipeline.process_frame(frame,**process_kwargs)
                    with violence_pipeline._state_lock:
                        latest_violence=float(violence_pipeline._last_conf)
                        violence_observation_score=float(getattr(violence_pipeline,'_last_calibrated_conf',latest_violence))
                        violence_raw_model_score=float(getattr(violence_pipeline,'_last_raw_conf',latest_violence))
                        violence_calibrated_probability=(violence_observation_score
                                                         if violence_calibration_active else None)
                        violence_id=int(getattr(violence_pipeline,'_observation_id',0))
                        violence_completed_at=float(getattr(violence_pipeline,'_completed_at',0))
                        violence_capture_timestamp=float(
                            getattr(violence_pipeline,'_last_source_capture_at',0)
                        )
                except Exception as exc:
                    violence_tick_failed=True
                    mark('violence','FAILED',type(exc).__name__)
            signal={}
            if weapon_engine is not None:
                weapon_completed_age=None
                weapon_observation_age=None
                try:
                    try:weapon_engine.process_frame(frame,observed_at=captured_at)
                    except TypeError:weapon_engine.process_frame(frame)
                    signal=weapon_engine.latest_signal() or {}
                    if int(signal.get('observation_id',0) or 0) > 0:
                        raw_weapon=signal.get('observation_score')
                        weapon_raw_model_score=float(signal.get('score',0.0) if raw_weapon is None else raw_weapon)
                        candidate_weapon_calibrated=signal.get('calibratedProbability')
                        weapon_calibration_status=str(signal.get('calibrationStatus','unverified'))
                        if (candidate_weapon_calibrated is not None and
                                weapon_calibration_status in {'calibrated','calibrated-candidate'}):
                            weapon_calibrated_probability=float(candidate_weapon_calibrated)
                        else:
                            weapon_calibrated_probability=None
                    reason=str(signal.get('reason',''))
                    if signal.get('failed') or reason.startswith(('inference-error:', 'model-load-failed:')):
                        mark('weapon','FAILED',reason)
                    elif signal.get('enabled') is False:
                        mark('weapon','DISABLED',reason)
                    elif signal.get('loading'):
                        mark('weapon','DEGRADED','Model loading')
                    elif reason == 'ok':
                        mark('weapon','OK')
                        weapon_completed_age=_monotonic_age_seconds(signal.get('completed_at'), time.monotonic())
                        try:
                            raw_observation_age=signal.get('observation_age_ms')
                            weapon_observation_age=max(0.0, float(raw_observation_age)/1000.0)
                        except (TypeError, ValueError):
                            weapon_observation_age=None
                        if (int(signal.get('observation_id',0)) > 0 and
                                ((weapon_completed_age is not None and weapon_completed_age >= MODALITY_STALE_AFTER_SECONDS) or
                                 (signal.get('observation_valid',True) is False and weapon_observation_age is not None and
                                  weapon_observation_age >= MODALITY_STALE_AFTER_SECONDS))):
                            age=max(value for value in (weapon_completed_age, weapon_observation_age) if value is not None)
                            mark('weapon','STALE',f'No completed weapon observation for {age:.1f}s')
                except Exception as exc:mark('weapon','FAILED',type(exc).__name__)
            if person_future is not None and person_future.done():
                try:
                    input_size, source_size = person_future_sizes
                    tracks=_scale_person_tracks(person_future.result(), input_size, source_size)
                    mark('person','OK')
                    telemetry["person_completed"] += 1
                except Exception as exc:
                    tracks=[]
                    mark('person','FAILED',type(exc).__name__)
                person_future=None
            if person_detector is not None and person_detector.enabled and person_future is None and frame_idx%max(1,int(config.get('person_interval',3)))==0:
                person_future_sizes=((frame.shape[1],frame.shape[0]),(width,height))
                person_future=executor.submit(person_detector.detect,frame)
            stage_inference_wait_ms = (time.perf_counter() - t_inference) * 1000.0
            weapon_score=float(signal.get('score',0.0))
            weapon_id=int(signal.get('observation_id',0))
            versions=(violence_id,weapon_id)
            fresh_violence=violence_id>0 and violence_id!=previous_versions[0]
            fresh_weapon=weapon_id>0 and weapon_id!=previous_versions[1] and signal.get('observation_valid',True)
            if fresh_violence or fresh_weapon:
                sample_time=max(violence_completed_at if fresh_violence else 0,float(signal.get('completed_at',0)) if fresh_weapon else 0,time.monotonic())
                sequence=max(sequence+1,int(sample_time*1_000_000))
                violence_candidate={
                    'source':'violence',
                    'score':violence_observation_score,
                    'raw_model_score':violence_raw_model_score,
                    'calibrated_probability':violence_calibrated_probability,
                    'calibration_status':violence_calibration_status if violence_calibrated_probability is not None else 'unverified',
                }
                weapon_candidate={
                    'source':'weapon',
                    'score':float(signal.get('observation_score',weapon_score)),
                    'raw_model_score':weapon_raw_model_score,
                    'calibrated_probability':weapon_calibrated_probability,
                    'calibration_status':weapon_calibration_status if weapon_calibrated_probability is not None else 'unverified',
                }
                selected_score=_select_fresh_observation_score(
                    fresh_violence=fresh_violence, violence=violence_candidate,
                    fresh_weapon=fresh_weapon, weapon=weapon_candidate)
                if selected_score is None:
                    raise RuntimeError("A fresh observation had no score candidate")
                observation_score=float(selected_score['score'])
                observation_score_source=str(selected_score['source'])
                observation_raw_model_score=selected_score['raw_model_score']
                observation_calibrated_probability=selected_score['calibrated_probability']
                observation_calibration_status=str(selected_score['calibration_status'])
                previous_versions=versions
                if fresh_violence:
                    telemetry["violence_completed"] += 1
                if fresh_weapon:
                    telemetry["weapon_completed"] += 1
                if telemetry["startup_first_observation_ms"] is None:
                    telemetry["startup_first_observation_ms"] = (time.monotonic() - t_entry) * 1000.0
            violence_is_threat=latest_violence>=policy.violence_threshold
            weapon_is_threat=weapon_score>=policy.weapon_threshold
            window=getattr(violence_pipeline,'window_status',{}) if violence_pipeline else {}
            now_monotonic=time.monotonic()
            violence_age_seconds=_monotonic_age_seconds(violence_completed_at, now_monotonic)
            if violence_pipeline and getattr(violence_pipeline,'last_error',''):
                mark('violence','FAILED',violence_pipeline.last_error)
            elif violence_pipeline and violence_pipeline.enabled and not violence_tick_failed:
                full_window=window.get('frames_collected',0)>=window.get('frames_required',32)>0
                if full_window and not window.get('valid',False):
                    mark('violence','DEGRADED',f'Invalid temporal window on {window_clock_source} timeline')
                elif (violence_id > 0 and violence_age_seconds is not None and
                        violence_age_seconds >= MODALITY_STALE_AFTER_SECONDS):
                    mark('violence','STALE',f'No completed violence observation for {violence_age_seconds:.1f}s')
                elif window.get('valid',False):
                    mark('violence','OK')
            person_stats={}
            if person_detector is not None:
                try:
                    person_stats=person_detector.latest_counting_stats()
                except Exception as exc:
                    person_stats={}
                    mark('person','DEGRADED',f'counting stats unavailable: {type(exc).__name__}')
            result=default_result()
            result.update({
                'is_threat':violence_is_threat or weapon_is_threat,
                'threat_confidence':max(latest_violence,weapon_score)*100,
                'violence_conf':latest_violence,'weapon_score':weapon_score,
                'weapon_labels':list(signal.get('labels',[])),'weapon_bbox':_normalize_bbox(signal.get('bbox')),
                'tracks':tracks,'person_count':len(tracks),'active_track_count':len(tracks),'motion_score':motion,
                'video_width':width,'video_height':height,'frame_idx':frame_idx,'timestamp':time.time(),
                'inference_sequence':sequence,'inference_sample_time':sample_time,
                'inference_generation':runtime_generation,
                'violence_observation_id':violence_id,'weapon_observation_id':weapon_id,
                'violence_capture_timestamp':violence_capture_timestamp,
                'violence_observation_age_ms':(violence_age_seconds*1000 if violence_age_seconds is not None else None),
                'weapon_observation_age_ms':signal.get('observation_age_ms'),
                'observation_score':observation_score,'observation_valid':bool(sequence),
                'observation_score_source':observation_score_source,
                'observation_raw_model_score':observation_raw_model_score,
                'observation_calibrated_probability':observation_calibrated_probability,
                'observation_calibration_status':observation_calibration_status,
                'violence_raw_model_score':violence_raw_model_score,
                'violence_calibrated_probability':violence_calibrated_probability,
                'violence_calibration_status':violence_calibration_status,
                'weapon_raw_model_score':weapon_raw_model_score,
                'weapon_calibrated_probability':weapon_calibrated_probability,
                'weapon_calibration_status':weapon_calibration_status,
                'capture_timestamp':captured_at,'processing_latency_ms':max(0,(_capture_now()-captured_at)*1000),
                'window_span_seconds':window.get('span_seconds',0),'window_valid':window.get('valid',False),
                'window_clock_source':window_clock_source,'source_sample_timestamp':window_timestamp,
                'frames_collected':window.get('frames_collected',0),'frames_required':window.get('frames_required',32),
                'pipeline_health':dict(health),'decision_config':policy.to_dict(),
                'visible_person_count':int(person_stats.get('visible_person_count',0)),
                'unique_person_estimate_window':person_stats.get('unique_person_estimate_window'),
                'track_failure_flags':dict(person_stats.get('track_failure_flags') or {}),
                'person_tracker':str(person_stats.get('person_tracker','') or ''),
            })
            # Additive worker telemetry (SC-2 additive; WT-13 locked names).
            # Cross-boundary stamps only ever diff within the declared capture
            # clock base; QPC is used for worker-internal durations.
            if capture_clock_base == "perf-qpc":
                t_dequeue_base, enqueued_base = t_dequeue_qpc, enqueued_at_qpc
            else:
                t_dequeue_base, enqueued_base = t_dequeue, enqueued_at
            result.update({
                'processRunId': process_run_id,
                'workerPid': worker_pid,
                'captureClockBase': capture_clock_base,
                'queuePolicy': queue_policy,
                'personCompletedCount': telemetry['person_completed'],
                'violenceCompletedCount': telemetry['violence_completed'],
                'weaponCompletedCount': telemetry['weapon_completed'],
                'active_track_count': len(tracks),
                'frameQueueDroppedDerived': telemetry['frame_queue_dropped_derived'],
                'frameQueueDiscardedByPolicy': telemetry['frame_queue_discarded_by_policy'],
                'frameQueueDiscardedAtReset': telemetry['frame_queue_discarded_at_reset'],
                'resultQueueDropped': telemetry['result_queue_dropped'],
                'capturedAtMonoMs': captured_at * 1000.0,
                'inferenceStartedAtMonoMs': t_dequeue_base * 1000.0,
                'dequeuedAtMonoMs': t_dequeue_base * 1000.0,
                'frameAgeMs': (t_dequeue_base - captured_at) * 1000.0,
                'frameAgeClockSource': 'monotonic-capture',
                'stagePreprocessMs': stage_preprocess_ms,
                'stageInferenceWaitMs': stage_inference_wait_ms,
                'stageSerializeMs': last_put_ms,
                'startupModelLoadMs': telemetry['startup_model_load_ms'],
                'startupFirstFrameMs': telemetry['startup_first_frame_ms'],
                'startupFirstResultMs': telemetry['startup_first_result_ms'],
                'startupFirstObservationMs': telemetry['startup_first_observation_ms'],
            })
            if enqueued_base is not None:
                result.update({
                    'enqueuedAtMonoMs': enqueued_base * 1000.0,
                    'stageCaptureToQueueMs': (enqueued_base - captured_at) * 1000.0,
                    'stageEnqueueToDequeueMs': (t_dequeue_base - enqueued_base) * 1000.0,
                })
            if backlog_frames is not None:
                result['backlogFrames'] = backlog_frames
            counting_stats_fn = getattr(person_detector, "latest_counting_stats", None)
            if callable(counting_stats_fn):
                try:
                    counting_stats = counting_stats_fn()
                except Exception as exc:
                    counting_stats = None
                    mark('tracking','DEGRADED',type(exc).__name__)
                if isinstance(counting_stats, dict):
                    for stats_key in ("visible_person_count", "unique_person_estimate_window",
                                      "track_failure_flags", "person_tracker"):
                        if stats_key in counting_stats:
                            result[stats_key] = counting_stats[stats_key]
            depth = _queue_depth(result_queue)
            if depth is not None:
                result['resultQueueDepth'] = depth
            t_put = time.perf_counter()
            try:
                result_queue.put(result,timeout=.1)
            except Full:
                telemetry['result_queue_dropped'] += 1
                mark('delivery','DEGRADED','Result queue full; observation delivery delayed')
            else:
                if telemetry['startup_first_result_ms'] is None:
                    telemetry['startup_first_result_ms'] = (time.monotonic() - t_entry) * 1000.0
            # Serialization cost can only be known after the put; it rides the
            # next result (first result carries None), like the counters.
            last_put_ms = (time.perf_counter() - t_put) * 1000.0
    finally:
        if weapon_engine is not None and hasattr(weapon_engine,'close'):weapon_engine.close()
        executor.shutdown(wait=True,cancel_futures=True)
        if violence_pipeline is not None and hasattr(violence_pipeline,'_inference_executor'):
            violence_pipeline._inference_executor.shutdown(wait=True,cancel_futures=True)
