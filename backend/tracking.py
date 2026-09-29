"""Box-only multi-object trackers for the Sentinel person path (S-04 / WT-22).

Implements, from the published algorithms:

* ``ByteTracker``  — ByteTrack (Zhang et al., arXiv:2110.06864, MIT). Two-stage
  association: high-score detections first against all live/lost tracks, then
  low-score detections against the still-unmatched *tracked* tracks, then new
  tracks from unmatched high-score detections with a higher activation
  threshold.
* ``OCSortTracker`` — compact observation-centric variant of OC-SORT
  (Cao et al., arXiv:2203.14360, MIT): direction/momentum-consistent cost and
  observation-centric recovery after a gap.
* ``LegacyIouTracker`` — the tracking that existed in ``person_detector.py``
  before this change (greedy IoU>0.3 assignment, tracks lost immediately on a
  missed frame). Kept ONLY as the labelled A/B baseline for evaluation.

NO ReID / appearance features anywhere: association uses geometry only (IoU and
box-centre direction). This is enforced structurally — the update API accepts
detections as boxes+scores and nothing else, and the trackers never receive
pixel data.

Track-failure taxonomy (heuristic, surfaced as telemetry, never silently
absorbed): ``id_switch``, ``re_entry``, ``merge_split``, ``dropout``, ``drift``.
The counters are *suspicion* counters derived from box geometry, not labels of
ground truth; every event is recorded with the frame index and the track ids
involved so a reviewer can audit them.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment

FAILURE_FLAG_NAMES = ("id_switch", "re_entry", "merge_split", "dropout", "drift")

DEFAULT_TRACKER_PARAMS: dict[str, float] = {
    # ByteTrack-compatible defaults (ultralytics bytetrack.yaml class defaults,
    # except new_track_thresh which the paper leaves equal to track_thresh so a
    # detection above the tracking threshold can start a track).
    "track_thresh": 0.5,
    "low_thresh": 0.1,
    "new_track_thresh": 0.5,
    "match_thresh": 0.8,
    "track_buffer": 30,
    "frame_rate": 30.0,
    # Failure-taxonomy heuristic thresholds.
    "reentry_iou": 0.3,
    "merge_iou": 0.8,
    "split_iou": 0.5,
    # A match below this IoU is a large motion correction. It must stay above
    # the association floor (IoU >= 1 - match_thresh = 0.2) or the flag could
    # never fire.
    "drift_iou": 0.3,
}


def xyxy_to_xyah(box: Sequence[float]) -> np.ndarray:
    x1, y1, x2, y2 = (float(value) for value in box[:4])
    width = max(1e-6, x2 - x1)
    height = max(1e-6, y2 - y1)
    return np.array([x1 + width / 2.0, y1 + height / 2.0, width / height, height], dtype=np.float64)


def xyah_to_xyxy(state: Sequence[float]) -> list[float]:
    cx, cy, aspect, height = (float(value) for value in state[:4])
    width = max(1e-6, aspect * height)
    return [cx - width / 2.0, cy - height / 2.0, cx + width / 2.0, cy + height / 2.0]


def box_iou(box_a: Sequence[float], box_b: Sequence[float]) -> float:
    ax1, ay1, ax2, ay2 = (float(value) for value in box_a[:4])
    bx1, by1, bx2, by2 = (float(value) for value in box_b[:4])
    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return float(inter / union) if union > 0.0 else 0.0


def iou_matrix(boxes_a: np.ndarray, boxes_b: np.ndarray) -> np.ndarray:
    """Vectorised pairwise IoU. ``boxes_*`` are ``(N, 4)`` xyxy arrays."""
    if boxes_a.size == 0 or boxes_b.size == 0:
        return np.zeros((len(boxes_a), len(boxes_b)), dtype=np.float64)
    a = np.asarray(boxes_a, dtype=np.float64).reshape(-1, 4)
    b = np.asarray(boxes_b, dtype=np.float64).reshape(-1, 4)
    inter_x1 = np.maximum(a[:, None, 0], b[None, :, 0])
    inter_y1 = np.maximum(a[:, None, 1], b[None, :, 1])
    inter_x2 = np.minimum(a[:, None, 2], b[None, :, 2])
    inter_y2 = np.minimum(a[:, None, 3], b[None, :, 3])
    inter_w = np.clip(inter_x2 - inter_x1, 0.0, None)
    inter_h = np.clip(inter_y2 - inter_y1, 0.0, None)
    inter = inter_w * inter_h
    area_a = np.clip(a[:, 2] - a[:, 0], 0.0, None) * np.clip(a[:, 3] - a[:, 1], 0.0, None)
    area_b = np.clip(b[:, 2] - b[:, 0], 0.0, None) * np.clip(b[:, 3] - b[:, 1], 0.0, None)
    union = area_a[:, None] + area_b[None, :] - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        iou = np.where(union > 0.0, inter / union, 0.0)
    return np.nan_to_num(iou, nan=0.0)


class KalmanFilterXYAH:
    """Constant-velocity Kalman filter in (centre-x, centre-y, aspect, height)."""

    def __init__(self, std_weight_position: float = 1.0 / 20.0, std_weight_velocity: float = 1.0 / 160.0):
        self.std_weight_position = std_weight_position
        self.std_weight_velocity = std_weight_velocity
        self._motion = np.eye(8, dtype=np.float64)
        for index in range(4):
            self._motion[index, index + 4] = 1.0
        self._observation = np.eye(4, 8, dtype=np.float64)

    def initiate(self, measurement: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
        mean = np.zeros(8, dtype=np.float64)
        mean[:4] = np.asarray(measurement, dtype=np.float64)
        height = max(1e-6, float(measurement[3]))
        std = np.array([
            2 * self.std_weight_position * height,
            2 * self.std_weight_position * height,
            1e-2,
            2 * self.std_weight_position * height,
            10 * self.std_weight_velocity * height,
            10 * self.std_weight_velocity * height,
            1e-5,
            10 * self.std_weight_velocity * height,
        ])
        return mean, np.diag(np.square(std))

    def predict(self, mean: np.ndarray, covariance: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        height = max(1e-6, float(mean[3]))
        std = np.array([
            self.std_weight_position * height,
            self.std_weight_position * height,
            1e-2,
            self.std_weight_position * height,
            self.std_weight_velocity * height,
            self.std_weight_velocity * height,
            1e-5,
            self.std_weight_velocity * height,
        ])
        motion_cov = np.diag(np.square(std))
        mean = self._motion @ mean
        covariance = self._motion @ covariance @ self._motion.T + motion_cov
        return mean, covariance

    def project(self, mean: np.ndarray, covariance: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        height = max(1e-6, float(mean[3]))
        std = np.array([
            self.std_weight_position * height,
            self.std_weight_position * height,
            1e-1,
            self.std_weight_position * height,
        ])
        measurement_cov = np.diag(np.square(std))
        projected_mean = self._observation @ mean
        projected_cov = self._observation @ covariance @ self._observation.T + measurement_cov
        return projected_mean, projected_cov

    def update(self, mean: np.ndarray, covariance: np.ndarray,
               measurement: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
        projected_mean, projected_cov = self.project(mean, covariance)
        gain = np.linalg.solve(projected_cov, self._observation @ covariance).T
        innovation = np.asarray(measurement, dtype=np.float64) - projected_mean
        new_mean = mean + gain @ innovation
        new_covariance = covariance - gain @ projected_cov @ gain.T
        return new_mean, new_covariance


@dataclass
class TrackFailureTelemetry:
    """Suspicion counters for the track-failure taxonomy (heuristic)."""

    counters: dict[str, int] = field(default_factory=lambda: {name: 0 for name in FAILURE_FLAG_NAMES})
    events: deque = field(default_factory=lambda: deque(maxlen=64))
    last_frame_index: int = 0
    _drained: dict[str, int] = field(default_factory=dict)

    def record(self, name: str, frame_index: int, **details: Any) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1
        event = {"flag": name, "frame_index": int(frame_index)}
        event.update({key: (int(value) if isinstance(value, (int, np.integer)) else value)
                      for key, value in details.items()})
        self.events.append(event)

    def drain_deltas(self) -> dict[str, int]:
        """Counters since the previous drain (consumed by the counting window)."""
        deltas: dict[str, int] = {}
        for name in FAILURE_FLAG_NAMES:
            current = int(self.counters.get(name, 0))
            previous = int(self._drained.get(name, 0))
            deltas[name] = max(0, current - previous)
            self._drained[name] = current
        return deltas

    def snapshot(self) -> dict[str, int]:
        return {name: int(self.counters.get(name, 0)) for name in FAILURE_FLAG_NAMES}

    def reset(self) -> None:
        for name in FAILURE_FLAG_NAMES:
            self.counters[name] = 0
        self.events.clear()
        self._drained.clear()


@dataclass
class Track:
    track_id: int
    mean: np.ndarray
    covariance: np.ndarray
    score: float
    frame_index: int
    bbox: list[float]
    state: str = "new"          # new | tracked | lost
    hits: int = 1
    time_since_update: int = 0
    first_frame_index: int = 0
    last_observation: Optional[list[float]] = None
    previous_observation: Optional[list[float]] = None
    recovery_count: int = 0

    @property
    def center(self) -> tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2.0, (self.bbox[1] + self.bbox[3]) / 2.0)


def _hungarian_assign(cost: np.ndarray, max_cost: float) -> list[tuple[int, int]]:
    """Deterministic minimum-cost assignment, gated by ``max_cost``."""
    if cost.size == 0:
        return []
    rows, cols = linear_sum_assignment(cost)
    return [(int(row), int(col)) for row, col in zip(rows, cols) if cost[row, col] <= max_cost]


class BaseTracker:
    """Shared bookkeeping: Kalman predict, telemetry hooks, output formatting."""

    name = "base"

    def __init__(self, **params: Any):
        merged = dict(DEFAULT_TRACKER_PARAMS)
        unknown = set(params) - set(merged)
        if unknown:
            raise ValueError(f"unknown tracker parameter(s): {sorted(unknown)}")
        merged.update(params)
        self.params = merged
        self.track_thresh = float(merged["track_thresh"])
        self.low_thresh = float(merged["low_thresh"])
        self.new_track_thresh = float(merged["new_track_thresh"])
        self.match_thresh = float(merged["match_thresh"])
        self.track_buffer = int(merged["track_buffer"])
        self.frame_rate = float(merged["frame_rate"])
        self.telemetry = TrackFailureTelemetry()
        self.tracks: list[Track] = []
        self._next_id = 1
        self._frame_index = 0
        self._removed_history: deque = deque(maxlen=256)  # (frame_index, track_id, last_bbox)

    @property
    def frame_index(self) -> int:
        return self._frame_index

    def reset(self) -> None:
        self.tracks.clear()
        self._next_id = 1
        self._frame_index = 0
        self._removed_history.clear()
        self.telemetry.reset()

    # -- geometry helpers -------------------------------------------------
    @staticmethod
    def _to_boxes(detections: np.ndarray) -> np.ndarray:
        detections = np.asarray(detections, dtype=np.float64)
        if detections.size == 0:
            return np.zeros((0, 5), dtype=np.float64)
        if detections.ndim == 1:
            detections = detections.reshape(1, -1)
        return detections[:, :5]

    def _predict_all(self) -> None:
        for track in self.tracks:
            track.mean, track.covariance = self.kf.predict(track.mean, track.covariance)
            track.bbox = xyah_to_xyxy(track.mean)
            track.time_since_update += 1

    def _new_track(self, detection: Sequence[float], frame_index: int) -> Track:
        measurement = xyxy_to_xyah(detection[:4])
        mean, covariance = self.kf.initiate(measurement)
        track = Track(
            track_id=self._next_id,
            mean=mean,
            covariance=covariance,
            score=float(detection[4]),
            frame_index=frame_index,
            bbox=[float(value) for value in detection[:4]],
            state="tracked",
            hits=1,
            time_since_update=0,
            first_frame_index=frame_index,
            last_observation=[float(value) for value in detection[:4]],
        )
        self._next_id += 1
        self.tracks.append(track)
        return track

    def _apply_detection(self, track: Track, detection: Sequence[float], frame_index: int) -> float:
        """Kalman update; returns the IoU between prediction and measurement."""
        predicted = list(track.bbox)
        measurement = xyxy_to_xyah(detection[:4])
        # time_since_update was incremented for every track by _predict_all, so a
        # track matched on consecutive frames has 1 here and 0 missed frames.
        gap_frames = max(0, int(track.time_since_update) - 1)
        track.mean, track.covariance = self.kf.update(track.mean, track.covariance, measurement)
        was_lost = gap_frames > 0
        track.previous_observation = track.last_observation
        track.last_observation = [float(value) for value in detection[:4]]
        track.bbox = xyah_to_xyxy(track.mean)
        track.score = float(detection[4])
        track.hits += 1
        track.time_since_update = 0
        track.state = "tracked"
        matched_iou = box_iou(predicted, detection[:4])
        if was_lost:
            track.recovery_count += 1
            self.telemetry.record("dropout", frame_index, track_id=track.track_id, gap_frames=gap_frames)
        return matched_iou

    def _retire_stale(self) -> None:
        staying: list[Track] = []
        for track in self.tracks:
            if track.state == "lost" and track.time_since_update > self.track_buffer:
                self._removed_history.append((self._frame_index, track.track_id, list(track.bbox)))
                continue
            staying.append(track)
        self.tracks = staying

    # -- taxonomy heuristics ---------------------------------------------
    def _flag_identity_handoff(self, new_track: Track, frame_index: int) -> None:
        """New track overlapping a recently removed track's last box."""
        best: Optional[tuple[int, int, float]] = None  # (frame_index, track_id, iou)
        for removed_frame, removed_id, removed_bbox in reversed(self._removed_history):
            gap = frame_index - removed_frame
            if gap > self.track_buffer:
                break
            overlap = box_iou(new_track.bbox, removed_bbox)
            if overlap >= float(self.params["reentry_iou"]):
                best = (removed_frame, removed_id, overlap)
                break
        if best is None:
            return
        removed_frame, removed_id, overlap = best
        gap = frame_index - removed_frame
        if gap <= 2:
            self.telemetry.record("id_switch", frame_index, new_track=new_track.track_id,
                                  old_track=removed_id, gap_frames=gap, overlap=round(float(overlap), 4))
        else:
            self.telemetry.record("re_entry", frame_index, new_track=new_track.track_id,
                                  old_track=removed_id, gap_frames=gap, overlap=round(float(overlap), 4))

    def _flag_merge_split(self, frame_index: int, detections: np.ndarray,
                          matched_pairs: Sequence[tuple[Track, int]]) -> None:
        tracked = [track for track in self.tracks if track.state == "tracked"]
        if len(tracked) >= 2:
            boxes = np.asarray([track.bbox for track in tracked], dtype=np.float64)
            overlaps = iou_matrix(boxes, boxes)
            threshold = float(self.params["merge_iou"])
            for left in range(len(tracked)):
                for right in range(left + 1, len(tracked)):
                    if overlaps[left, right] >= threshold:
                        self.telemetry.record("merge_split", frame_index, kind="merge",
                                              track_a=tracked[left].track_id, track_b=tracked[right].track_id)
        if len(detections) and self._removed_history:
            recent = [entry for entry in self._removed_history if frame_index - entry[0] <= 1]
            for detection in detections:
                hits = [entry[1] for entry in recent
                        if box_iou(detection[:4], entry[2]) >= float(self.params["split_iou"])]
                if len(hits) >= 2:
                    self.telemetry.record("merge_split", frame_index, kind="split",
                                          old_tracks=",".join(str(value) for value in hits))

    def _flag_drift(self, frame_index: int, track: Track, matched_iou: float) -> None:
        if matched_iou < float(self.params["drift_iou"]):
            self.telemetry.record("drift", frame_index, track_id=track.track_id, matched_iou=round(float(matched_iou), 4))

    # -- public API -------------------------------------------------------
    @property
    def kf(self) -> KalmanFilterXYAH:
        if not hasattr(self, "_kf"):
            self._kf = KalmanFilterXYAH()
        return self._kf

    def update(self, detections: np.ndarray) -> list[dict[str, Any]]:
        raise NotImplementedError

    def output(self) -> list[dict[str, Any]]:
        return [
            {
                "track_id": track.track_id,
                "bbox": [float(value) for value in track.bbox],
                "confidence": float(track.score),
                "state": track.state,
                "hits": int(track.hits),
                "time_since_update": int(track.time_since_update),
            }
            for track in self.tracks if track.state == "tracked" and track.time_since_update == 0
        ]

    def snapshot_stats(self) -> dict[str, Any]:
        return {
            "tracker": self.name,
            "frame_index": int(self._frame_index),
            "active_tracks": int(sum(1 for track in self.tracks
                                     if track.state == "tracked" and track.time_since_update == 0)),
            "live_tracks": int(len(self.tracks)),
            "track_failure_flags": self.telemetry.snapshot(),
        }


class ByteTracker(BaseTracker):
    """ByteTrack two-stage association (arXiv:2110.06864)."""

    name = "bytetrack"

    def update(self, detections: np.ndarray) -> list[dict[str, Any]]:
        self._frame_index += 1
        frame_index = self._frame_index
        detections = self._to_boxes(detections)
        self._predict_all()

        high = detections[detections[:, 4] >= self.track_thresh] if len(detections) else detections
        low = detections[(detections[:, 4] >= self.low_thresh) & (detections[:, 4] < self.track_thresh)] if len(detections) else detections

        pool = [track for track in self.tracks if track.state in ("tracked", "lost", "new")]
        matched_pairs: list[tuple[Track, int]] = []
        unmatched_ids = {track.track_id for track in pool}
        unmatched_high = set(range(len(high)))

        if len(pool) and len(high):
            pool_boxes = np.asarray([track.bbox for track in pool], dtype=np.float64)
            cost = 1.0 - iou_matrix(high[:, :4], pool_boxes)
            for row, col in _hungarian_assign(cost, self.match_thresh):
                track = pool[col]
                matched_iou = self._apply_detection(track, high[row], frame_index)
                self._flag_drift(frame_index, track, matched_iou)
                matched_pairs.append((track, row))
                unmatched_ids.discard(track.track_id)
                unmatched_high.discard(row)

        for track in pool:
            if track.track_id in unmatched_ids and track.state in ("tracked", "new"):
                track.state = "lost"

        # Stage 2: low-score detections against still-unmatched recent tracks.
        stage2_pool = [track for track in pool
                       if track.track_id in unmatched_ids and track.state == "lost" and track.time_since_update <= 1]
        if stage2_pool and len(low):
            pool_boxes = np.asarray([track.bbox for track in stage2_pool], dtype=np.float64)
            cost = 1.0 - iou_matrix(low[:, :4], pool_boxes)
            for row, col in _hungarian_assign(cost, 0.5):
                track = stage2_pool[col]
                matched_iou = self._apply_detection(track, low[row], frame_index)
                self._flag_drift(frame_index, track, matched_iou)
                unmatched_ids.discard(track.track_id)

        for index in sorted(unmatched_high):
            if high[index, 4] >= self.new_track_thresh:
                track = self._new_track(high[index], frame_index)
                self._flag_identity_handoff(track, frame_index)

        self._retire_stale()
        self._flag_merge_split(frame_index, high, matched_pairs)
        self.telemetry.last_frame_index = frame_index
        return self.output()


class OCSortTracker(BaseTracker):
    """Compact observation-centric SORT (arXiv:2203.14360)."""

    name = "ocsort"
    delta_t = 3
    inertia = 0.2
    angle_weight = 0.4
    recover_alpha = 0.2

    def _direction_cost(self, tracks: Sequence[Track], detections: np.ndarray) -> np.ndarray:
        cost = np.zeros((len(detections), len(tracks)), dtype=np.float64)
        for col, track in enumerate(tracks):
            if track.previous_observation is None or track.last_observation is None:
                continue
            previous_center = ((track.previous_observation[0] + track.previous_observation[2]) / 2.0,
                               (track.previous_observation[1] + track.previous_observation[3]) / 2.0)
            last_center = ((track.last_observation[0] + track.last_observation[2]) / 2.0,
                           (track.last_observation[1] + track.last_observation[3]) / 2.0)
            velocity = np.array([last_center[0] - previous_center[0], last_center[1] - previous_center[1]], dtype=np.float64)
            norm = float(np.linalg.norm(velocity))
            if norm <= 1e-6:
                continue
            velocity = velocity / norm
            for row in range(len(detections)):
                det_center = np.array([(detections[row, 0] + detections[row, 2]) / 2.0,
                                       (detections[row, 1] + detections[row, 3]) / 2.0], dtype=np.float64)
                offset = det_center - np.array(last_center, dtype=np.float64)
                offset_norm = float(np.linalg.norm(offset))
                if offset_norm <= 1e-6:
                    continue
                cosine = float(np.dot(velocity, offset / offset_norm))
                cost[row, col] += self.angle_weight * (1.0 - cosine)
        return cost

    def _recover_after_gap(self, track: Track, detection: Sequence[float], frame_index: int) -> None:
        """Observation-centric recovery: feed virtual interpolated observations."""
        gap = int(track.time_since_update)
        if gap <= 1 or track.last_observation is None:
            return
        start = np.asarray(track.last_observation, dtype=np.float64)
        end = np.asarray(detection[:4], dtype=np.float64)
        for step in range(1, gap):
            ratio = step / float(gap)
            virtual = start + (end - start) * ratio
            measurement = xyxy_to_xyah(virtual)
            track.mean, track.covariance = self.kf.update(track.mean, track.covariance, measurement)

    def update(self, detections: np.ndarray) -> list[dict[str, Any]]:
        self._frame_index += 1
        frame_index = self._frame_index
        detections = self._to_boxes(detections)
        self._predict_all()

        candidates = detections[detections[:, 4] >= self.track_thresh] if len(detections) else detections
        pool = [track for track in self.tracks if track.state in ("tracked", "lost", "new")]
        unmatched_ids = {track.track_id for track in pool}
        unmatched_det = set(range(len(candidates)))

        if len(pool) and len(candidates):
            pool_boxes = np.asarray([track.bbox for track in pool], dtype=np.float64)
            cost = 1.0 - iou_matrix(candidates[:, :4], pool_boxes)
            cost = cost + self._direction_cost(pool, candidates)
            for row, col in _hungarian_assign(cost, self.match_thresh):
                track = pool[col]
                self._recover_after_gap(track, candidates[row], frame_index)
                matched_iou = self._apply_detection(track, candidates[row], frame_index)
                self._flag_drift(frame_index, track, matched_iou)
                unmatched_ids.discard(track.track_id)
                unmatched_det.discard(row)

        for track in pool:
            if track.track_id in unmatched_ids and track.state in ("tracked", "new"):
                track.state = "lost"

        # Low-score confirmation pass against recent tracks only.
        low = detections[(detections[:, 4] >= self.low_thresh) & (detections[:, 4] < self.track_thresh)] if len(detections) else detections
        recent = [track for track in pool if track.track_id in unmatched_ids and track.time_since_update <= 1]
        if len(low) and len(recent):
            pool_boxes = np.asarray([track.bbox for track in recent], dtype=np.float64)
            cost = 1.0 - iou_matrix(low[:, :4], pool_boxes)
            for row, col in _hungarian_assign(cost, 0.5):
                track = recent[col]
                matched_iou = self._apply_detection(track, low[row], frame_index)
                self._flag_drift(frame_index, track, matched_iou)
                unmatched_ids.discard(track.track_id)

        for index in sorted(unmatched_det):
            if candidates[index, 4] >= self.new_track_thresh:
                track = self._new_track(candidates[index], frame_index)
                self._flag_identity_handoff(track, frame_index)

        self._retire_stale()
        self._flag_merge_split(frame_index, candidates, [])
        self.telemetry.last_frame_index = frame_index
        return self.output()


class LegacyIouTracker(BaseTracker):
    """Pre-change behaviour of ``PersonDetector`` — A/B baseline only.

    Greedy IoU>0.3 assignment against the *current* track boxes; a track missed
    in one frame is dropped immediately; IDs are never re-used.
    """

    name = "iou_legacy"
    assign_iou = 0.3

    def update(self, detections: np.ndarray) -> list[dict[str, Any]]:
        self._frame_index += 1
        frame_index = self._frame_index
        detections = self._to_boxes(detections)
        used: set[int] = set()
        live: list[Track] = []
        matched_detections: set[int] = set()
        for index, detection in enumerate(detections):
            if detection[4] < self.low_thresh:
                continue
            best: Optional[Track] = None
            best_iou = 0.0
            for track in self.tracks:
                if track.track_id in used:
                    continue
                overlap = box_iou(detection[:4], track.bbox)
                if overlap > best_iou and overlap > self.assign_iou:
                    best_iou = overlap
                    best = track
            if best is None:
                best = self._new_track(detection, frame_index)
                self._flag_identity_handoff(best, frame_index)
            else:
                best.bbox = [float(value) for value in detection[:4]]
                best.score = float(detection[4])
                best.hits += 1
                best.last_observation = list(best.bbox)
            best.time_since_update = 0
            best.state = "tracked"
            used.add(best.track_id)
            matched_detections.add(index)
            live.append(best)
        for track in self.tracks:
            if track.track_id not in used:
                self._removed_history.append((frame_index, track.track_id, list(track.bbox)))
        self.tracks = live
        self._flag_merge_split(frame_index, detections, [])
        self.telemetry.last_frame_index = frame_index
        return self.output()


TRACKER_FACTORIES = {
    "bytetrack": ByteTracker,
    "ocsort": OCSortTracker,
    "iou_legacy": LegacyIouTracker,
}


def create_tracker(name: str = "bytetrack", **params: Any) -> BaseTracker:
    key = str(name or "").strip().lower()
    if key not in TRACKER_FACTORIES:
        raise ValueError(f"unknown tracker {name!r}; expected one of {sorted(TRACKER_FACTORIES)}")
    return TRACKER_FACTORIES[key](**params)
