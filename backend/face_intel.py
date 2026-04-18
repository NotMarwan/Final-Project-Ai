from __future__ import annotations

import base64
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


@dataclass
class FaceIntelConfig:
    enabled: bool = False
    detector_backend: str = "none"
    known_match_threshold: float = 0.45
    unknown_match_threshold: float = 0.30
    unknown_match_relax_factor: float = 1.35
    unknown_min_iou: float = 0.08
    unknown_strong_iou: float = 0.55
    unknown_embedding_weight: float = 0.70
    unknown_iou_weight: float = 0.30
    max_unknown_age_frames: int = 90
    min_face_size: int = 36
    known_registry_path: str = "./known_faces_registry.json"

    @classmethod
    def from_settings(cls, settings: dict, env: dict) -> "FaceIntelConfig":
        face_cfg = settings.get("face_intel") or {}
        if not isinstance(face_cfg, dict):
            face_cfg = {}

        return cls(
            enabled=_as_bool(env.get("FACE_INTEL_ENABLED"), _as_bool(face_cfg.get("enabled"), False)),
            detector_backend=str(env.get("FACE_DETECTOR_BACKEND", face_cfg.get("detector_backend", "none"))).strip().lower(),
            known_match_threshold=_as_float(env.get("FACE_KNOWN_MATCH_THRESHOLD"), _as_float(face_cfg.get("known_match_threshold"), 0.45)),
            unknown_match_threshold=_as_float(env.get("FACE_UNKNOWN_MATCH_THRESHOLD"), _as_float(face_cfg.get("unknown_match_threshold"), 0.30)),
            unknown_match_relax_factor=_as_float(
                env.get("FACE_UNKNOWN_MATCH_RELAX_FACTOR"),
                _as_float(face_cfg.get("unknown_match_relax_factor"), 1.35),
            ),
            unknown_min_iou=_as_float(env.get("FACE_UNKNOWN_MIN_IOU"), _as_float(face_cfg.get("unknown_min_iou"), 0.08)),
            unknown_strong_iou=_as_float(env.get("FACE_UNKNOWN_STRONG_IOU"), _as_float(face_cfg.get("unknown_strong_iou"), 0.55)),
            unknown_embedding_weight=_as_float(
                env.get("FACE_UNKNOWN_EMBEDDING_WEIGHT"),
                _as_float(face_cfg.get("unknown_embedding_weight"), 0.70),
            ),
            unknown_iou_weight=_as_float(env.get("FACE_UNKNOWN_IOU_WEIGHT"), _as_float(face_cfg.get("unknown_iou_weight"), 0.30)),
            max_unknown_age_frames=_as_int(env.get("FACE_MAX_UNKNOWN_AGE_FRAMES"), _as_int(face_cfg.get("max_unknown_age_frames"), 90)),
            min_face_size=_as_int(env.get("FACE_MIN_FACE_SIZE"), _as_int(face_cfg.get("min_face_size"), 36)),
            known_registry_path=str(env.get("FACE_KNOWN_REGISTRY_PATH", face_cfg.get("known_registry_path", "./known_faces_registry.json"))),
        )


class FaceIntelEngine:
    def __init__(self, config: FaceIntelConfig, base_dir: Path):
        self.config = config
        self.base_dir = base_dir
        self._lock = threading.RLock()
        self._frame_index = 0
        self._unknown_counter = 0
        self._unknown_tracks: Dict[str, Dict[str, object]] = {}
        self._known_registry: List[Dict[str, object]] = []
        self._last_summary: Dict[str, object] = self._empty_summary()
        self._cascade = None

        self._init_detector()
        self._load_known_registry()

    @classmethod
    def from_settings(cls, settings: dict, env: dict, base_dir: Path) -> "FaceIntelEngine":
        return cls(FaceIntelConfig.from_settings(settings, env), base_dir)

    def _registry_path(self) -> Path:
        raw = Path(self.config.known_registry_path)
        return raw if raw.is_absolute() else self.base_dir / raw

    def _init_detector(self) -> None:
        if self.config.detector_backend != "haar":
            return
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        if not cascade_path.exists():
            return
        detector = cv2.CascadeClassifier(str(cascade_path))
        if detector.empty():
            return
        self._cascade = detector

    def _load_known_registry(self) -> None:
        path = self._registry_path()
        if not path.exists():
            self._known_registry = []
            return

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._known_registry = []
            return

        records = payload.get("people") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            self._known_registry = []
            return

        loaded: List[Dict[str, object]] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            person_id = str(item.get("person_id", "")).strip()
            if not person_id:
                continue

            display_name = str(item.get("display_name", person_id)).strip() or person_id
            role = str(item.get("role", "")).strip()
            raw_embeddings = item.get("embeddings", [])
            embeddings: List[np.ndarray] = []
            if isinstance(raw_embeddings, list):
                for raw in raw_embeddings:
                    if not isinstance(raw, list):
                        continue
                    vec = np.asarray(raw, dtype=np.float32)
                    if vec.size == 0:
                        continue
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec = vec / norm
                    embeddings.append(vec)
            loaded.append(
                {
                    "person_id": person_id,
                    "display_name": display_name,
                    "role": role,
                    "embeddings": embeddings,
                }
            )
        self._known_registry = loaded

    def _serialize_registry(self) -> List[Dict[str, object]]:
        serialized: List[Dict[str, object]] = []
        for person in self._known_registry:
            embeddings = person.get("embeddings", [])
            raw_embeddings: List[List[float]] = []
            if isinstance(embeddings, list):
                for emb in embeddings:
                    if isinstance(emb, np.ndarray):
                        raw_embeddings.append([float(x) for x in emb.tolist()])
            serialized.append(
                {
                    "person_id": str(person.get("person_id", "")).strip(),
                    "display_name": str(person.get("display_name", "")).strip(),
                    "role": str(person.get("role", "")).strip(),
                    "embeddings": raw_embeddings,
                }
            )
        return serialized

    def _save_known_registry(self) -> None:
        path = self._registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"people": self._serialize_registry()}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _find_person(self, person_id: str) -> Tuple[int, Optional[Dict[str, object]]]:
        target = person_id.strip()
        for idx, person in enumerate(self._known_registry):
            if str(person.get("person_id", "")).strip() == target:
                return idx, person
        return -1, None

    @staticmethod
    def _empty_summary() -> Dict[str, object]:
        return {
            "enabled": False,
            "detector": "none",
            "frameIndex": 0,
            "totalFaces": 0,
            "recognized": [],
            "unknownIds": [],
            "unknownCount": 0,
            "observations": [],
        }

    @staticmethod
    def _distance(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a - b))

    @staticmethod
    def _bbox_iou(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ax2, ay2 = ax + aw, ay + ah
        bx2, by2 = bx + bw, by + bh

        ix1 = max(ax, bx)
        iy1 = max(ay, by)
        ix2 = min(ax2, bx2)
        iy2 = min(ay2, by2)

        iw = max(0, ix2 - ix1)
        ih = max(0, iy2 - iy1)
        inter = float(iw * ih)
        if inter <= 0:
            return 0.0

        area_a = float(max(0, aw) * max(0, ah))
        area_b = float(max(0, bw) * max(0, bh))
        denom = area_a + area_b - inter
        if denom <= 0:
            return 0.0
        return inter / denom

    def list_known_people(self, include_embeddings: bool = False) -> List[Dict[str, object]]:
        people: List[Dict[str, object]] = []
        with self._lock:
            for person in self._known_registry:
                item = {
                    "personId": str(person.get("person_id", "")).strip(),
                    "displayName": str(person.get("display_name", "")).strip(),
                    "role": str(person.get("role", "")).strip(),
                    "embeddingCount": len(person.get("embeddings", [])),
                }
                if include_embeddings:
                    item["embeddings"] = [
                        [float(x) for x in emb.tolist()]
                        for emb in person.get("embeddings", [])
                        if isinstance(emb, np.ndarray)
                    ]
                people.append(item)
        return people

    def upsert_known_person(self, person_id: str, display_name: str, role: str = "") -> Dict[str, object]:
        pid = person_id.strip()
        if not pid:
            raise ValueError("person_id is required")

        display = display_name.strip() or pid
        with self._lock:
            idx, person = self._find_person(pid)
            if person is None:
                person = {
                    "person_id": pid,
                    "display_name": display,
                    "role": role.strip(),
                    "embeddings": [],
                }
                self._known_registry.append(person)
            else:
                person["display_name"] = display
                person["role"] = role.strip()
                self._known_registry[idx] = person
            self._save_known_registry()
            return {
                "personId": pid,
                "displayName": str(person.get("display_name", "")).strip(),
                "role": str(person.get("role", "")).strip(),
                "embeddingCount": len(person.get("embeddings", [])),
            }

    def get_known_person(self, person_id: str, include_embeddings: bool = False) -> Optional[Dict[str, object]]:
        pid = person_id.strip()
        if not pid:
            return None
        with self._lock:
            _idx, person = self._find_person(pid)
            if person is None:
                return None
            result = {
                "personId": str(person.get("person_id", "")).strip(),
                "displayName": str(person.get("display_name", "")).strip(),
                "role": str(person.get("role", "")).strip(),
                "embeddingCount": len(person.get("embeddings", [])),
            }
            if include_embeddings:
                result["embeddings"] = [
                    [float(x) for x in emb.tolist()]
                    for emb in person.get("embeddings", [])
                    if isinstance(emb, np.ndarray)
                ]
            return result

    def delete_known_person(self, person_id: str) -> bool:
        pid = person_id.strip()
        if not pid:
            return False
        with self._lock:
            idx, _person = self._find_person(pid)
            if idx < 0:
                return False
            self._known_registry.pop(idx)
            self._save_known_registry()
            return True

    def clear_person_embeddings(self, person_id: str) -> bool:
        pid = person_id.strip()
        if not pid:
            return False
        with self._lock:
            idx, person = self._find_person(pid)
            if person is None:
                return False
            person["embeddings"] = []
            self._known_registry[idx] = person
            self._save_known_registry()
            return True

    @staticmethod
    def _decode_base64_image(image_base64: str) -> np.ndarray:
        raw = image_base64.strip()
        if "," in raw and raw.lower().startswith("data:image"):
            raw = raw.split(",", 1)[1]
        binary = base64.b64decode(raw, validate=True)
        arr = np.frombuffer(binary, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("image decode failed")
        return image

    def _pick_enrollment_crop(self, image: np.ndarray) -> np.ndarray:
        detections = self.detect_faces(image, for_enrollment=True)
        if detections:
            x, y, w, h = detections[0]["bbox"]
            x2 = min(image.shape[1], x + w)
            y2 = min(image.shape[0], y + h)
            crop = image[max(0, y):y2, max(0, x):x2]
            if crop.size > 0:
                return crop
        return image

    def enroll_person_from_base64(self, person_id: str, image_base64: str, display_name: str = "", role: str = "") -> Dict[str, object]:
        pid = person_id.strip()
        if not pid:
            raise ValueError("person_id is required")
        if not image_base64.strip():
            raise ValueError("image_base64 is required")

        image = self._decode_base64_image(image_base64)
        crop = self._pick_enrollment_crop(image)
        embedding = self.extract_embedding(crop)

        with self._lock:
            idx, person = self._find_person(pid)
            if person is None:
                person = {
                    "person_id": pid,
                    "display_name": display_name.strip() or pid,
                    "role": role.strip(),
                    "embeddings": [],
                }
                self._known_registry.append(person)
                idx = len(self._known_registry) - 1
            else:
                if display_name.strip():
                    person["display_name"] = display_name.strip()
                if role.strip():
                    person["role"] = role.strip()

            embeddings = person.get("embeddings", [])
            if not isinstance(embeddings, list):
                embeddings = []
            embeddings.append(embedding)
            person["embeddings"] = embeddings
            self._known_registry[idx] = person
            self._save_known_registry()

            return {
                "personId": pid,
                "displayName": str(person.get("display_name", "")).strip(),
                "role": str(person.get("role", "")).strip(),
                "embeddingCount": len(person.get("embeddings", [])),
            }

    def reset_session(self, reason: str = "manual-reset") -> None:
        with self._lock:
            self._unknown_counter = 0
            self._unknown_tracks.clear()
            self._last_summary = self._empty_summary()
            self._last_summary["enabled"] = self.config.enabled
            self._last_summary["detector"] = self.config.detector_backend
            self._last_summary["resetReason"] = reason

    def detect_faces(self, frame: np.ndarray, for_enrollment: bool = False) -> List[Dict[str, object]]:
        if not self.config.enabled and not for_enrollment:
            return []
        if self.config.detector_backend != "haar" or self._cascade is None:
            return []

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        detections = self._cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(self.config.min_face_size, self.config.min_face_size),
        )
        faces: List[Dict[str, object]] = []
        for (x, y, w, h) in detections:
            faces.append({"bbox": (int(x), int(y), int(w), int(h)), "confidence": 1.0})
        return faces

    def extract_embedding(self, face_crop: np.ndarray) -> np.ndarray:
        if face_crop.size == 0:
            return np.zeros(34, dtype=np.float32)

        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)
        hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten().astype(np.float32)
        hist_sum = float(hist.sum())
        if hist_sum > 0:
            hist = hist / hist_sum
        stats = np.array(
            [
                float(gray.mean() / 255.0),
                float(gray.std() / 255.0),
            ],
            dtype=np.float32,
        )
        embedding = np.concatenate([hist, stats], axis=0)
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.astype(np.float32)

    def match_known_face(self, embedding: np.ndarray) -> Optional[Dict[str, object]]:
        best: Optional[Dict[str, object]] = None
        best_dist = 999.0

        with self._lock:
            people_snapshot = list(self._known_registry)

        for person in people_snapshot:
            for known_embedding in person["embeddings"]:
                if known_embedding.shape != embedding.shape:
                    continue
                dist = self._distance(embedding, known_embedding)
                if dist < best_dist:
                    best_dist = dist
                    best = person

        if best is None or best_dist > self.config.known_match_threshold:
            return None

        confidence = max(0.0, min(1.0, 1.0 - best_dist))
        return {
            "personId": best["person_id"],
            "label": best["display_name"],
            "confidence": round(confidence, 4),
            "distance": round(best_dist, 4),
        }

    def assign_unknown_id(self, embedding: np.ndarray, track_hint: Optional[Dict[str, object]] = None) -> str:
        current_bbox: Optional[Tuple[int, int, int, int]] = None
        if isinstance(track_hint, dict):
            raw_bbox = track_hint.get("bbox")
            if isinstance(raw_bbox, (list, tuple)) and len(raw_bbox) == 4:
                try:
                    current_bbox = (int(raw_bbox[0]), int(raw_bbox[1]), int(raw_bbox[2]), int(raw_bbox[3]))
                except Exception:
                    current_bbox = None

        with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            stale_ids = []
            for unknown_id, track in self._unknown_tracks.items():
                age = self._frame_index - int(track.get("lastSeenFrame", 0))
                if age > self.config.max_unknown_age_frames:
                    stale_ids.append(unknown_id)
            for unknown_id in stale_ids:
                self._unknown_tracks.pop(unknown_id, None)

            best_id = None
            best_iou = 0.0
            best_dist = 999.0
            best_score = 999.0
            for unknown_id, track in self._unknown_tracks.items():
                ref = track.get("embedding")
                if not isinstance(ref, np.ndarray) or ref.shape != embedding.shape:
                    continue
                dist = self._distance(embedding, ref)
                prev_bbox = track.get("bbox")
                iou = 0.0
                if current_bbox is not None and isinstance(prev_bbox, tuple) and len(prev_bbox) == 4:
                    iou = self._bbox_iou(current_bbox, prev_bbox)

                score = (
                    self.config.unknown_embedding_weight * dist
                    + self.config.unknown_iou_weight * (1.0 - iou)
                )

                if score < best_score:
                    best_score = score
                    best_dist = dist
                    best_iou = iou
                    best_id = unknown_id

            dist_ok = best_dist <= self.config.unknown_match_threshold
            relaxed_dist_ok = best_dist <= (self.config.unknown_match_threshold * self.config.unknown_match_relax_factor)
            iou_ok = best_iou >= self.config.unknown_min_iou
            strong_iou_ok = best_iou >= self.config.unknown_strong_iou

            should_reuse = False
            if best_id is not None:
                if dist_ok:
                    should_reuse = True
                elif strong_iou_ok and relaxed_dist_ok:
                    should_reuse = True
                elif iou_ok and dist_ok:
                    should_reuse = True

            if should_reuse and best_id is not None:
                self._unknown_tracks[best_id]["embedding"] = embedding
                self._unknown_tracks[best_id]["lastSeenFrame"] = self._frame_index
                self._unknown_tracks[best_id]["lastSeenAt"] = now_iso
                if current_bbox is not None:
                    self._unknown_tracks[best_id]["bbox"] = current_bbox
                self._unknown_tracks[best_id]["hitStreak"] = int(self._unknown_tracks[best_id].get("hitStreak", 0)) + 1
                return best_id

            self._unknown_counter += 1
            unknown_id = f"U-{self._unknown_counter:03d}"
            self._unknown_tracks[unknown_id] = {
                "embedding": embedding,
                "bbox": current_bbox,
                "firstSeenFrame": self._frame_index,
                "lastSeenFrame": self._frame_index,
                "firstSeenAt": now_iso,
                "lastSeenAt": now_iso,
                "hitStreak": 1,
            }
            return unknown_id

    def _unknown_details_for_ids(self, unknown_ids: List[str]) -> List[Dict[str, object]]:
        details: List[Dict[str, object]] = []
        with self._lock:
            for unknown_id in unknown_ids:
                track = self._unknown_tracks.get(unknown_id)
                if not track:
                    continue
                first_seen = int(track.get("firstSeenFrame", 0))
                last_seen = int(track.get("lastSeenFrame", first_seen))
                details.append(
                    {
                        "id": unknown_id,
                        "firstSeenFrame": first_seen,
                        "lastSeenFrame": last_seen,
                        "durationFrames": max(0, last_seen - first_seen + 1),
                        "firstSeenAt": str(track.get("firstSeenAt", "")),
                        "lastSeenAt": str(track.get("lastSeenAt", "")),
                        "hitStreak": int(track.get("hitStreak", 0)),
                        "lastBbox": list(track.get("bbox") or ()),
                    }
                )
        return details

    def analyze_frame(self, frame: np.ndarray) -> Dict[str, object]:
        with self._lock:
            self._frame_index += 1
            frame_idx = self._frame_index
        if not self.config.enabled:
            with self._lock:
                self._last_summary = self._empty_summary()
                self._last_summary["frameIndex"] = frame_idx
                return dict(self._last_summary)

        detections = sorted(
            self.detect_faces(frame),
            key=lambda d: (int(d["bbox"][1]), int(d["bbox"][0])),
        )
        recognized: List[Dict[str, object]] = []
        unknown_ids: List[str] = []
        observations: List[Dict[str, object]] = []

        for item in detections:
            x, y, w, h = item["bbox"]
            x2 = min(frame.shape[1], x + w)
            y2 = min(frame.shape[0], y + h)
            face_crop = frame[max(0, y):y2, max(0, x):x2]
            embedding = self.extract_embedding(face_crop)
            known = self.match_known_face(embedding)

            if known:
                face_id = str(known["personId"])
                label = str(known["label"])
                confidence = float(known["confidence"])
                if not any(p["personId"] == face_id for p in recognized):
                    recognized.append(known)
                kind = "known"
            else:
                face_id = self.assign_unknown_id(
                    embedding,
                    track_hint={"bbox": (int(x), int(y), int(w), int(h))},
                )
                label = face_id
                confidence = 0.0
                if face_id not in unknown_ids:
                    unknown_ids.append(face_id)
                kind = "unknown"

            observations.append(
                {
                    "id": face_id,
                    "label": label,
                    "kind": kind,
                    "confidence": round(confidence, 4),
                    "bbox": [int(x), int(y), int(w), int(h)],
                }
            )

        with self._lock:
            unknown_details = self._unknown_details_for_ids(unknown_ids)
            self._last_summary = {
                "enabled": True,
                "detector": self.config.detector_backend,
                "frameIndex": frame_idx,
                "totalFaces": len(observations),
                "recognized": recognized,
                "recognizedCount": len(recognized),
                "unknownIds": unknown_ids,
                "unknownCount": len(unknown_ids),
                "unknownDetails": unknown_details,
                "observations": observations,
            }
            return dict(self._last_summary)

    def current_summary(self) -> Dict[str, object]:
        with self._lock:
            return dict(self._last_summary)

    def status(self) -> Dict[str, object]:
        with self._lock:
            return {
                "enabled": self.config.enabled,
                "detectorBackend": self.config.detector_backend,
                "knownRegistryPath": str(self._registry_path()),
                "knownRegistryCount": len(self._known_registry),
                "unknownActiveCount": len(self._unknown_tracks),
                "frameIndex": self._frame_index,
                "thresholds": {
                    "knownMatch": self.config.known_match_threshold,
                    "unknownMatch": self.config.unknown_match_threshold,
                    "unknownMatchRelaxFactor": self.config.unknown_match_relax_factor,
                    "unknownMinIoU": self.config.unknown_min_iou,
                    "unknownStrongIoU": self.config.unknown_strong_iou,
                    "unknownEmbeddingWeight": self.config.unknown_embedding_weight,
                    "unknownIoUWeight": self.config.unknown_iou_weight,
                },
                "maxUnknownAgeFrames": self.config.max_unknown_age_frames,
                "lastSummary": dict(self._last_summary),
            }
