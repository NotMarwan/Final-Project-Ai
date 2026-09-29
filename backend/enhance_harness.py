"""Distortion and utility harness for image enhancement (WT-23).

Any enhanced artifact must be measurable against its original before it can be
used. The harness reports, for the original/derivative pair:

* ``psnrDb`` — peak signal-to-noise ratio (full-scale 255).
* ``ssim`` — structural similarity (11×11 Gaussian window, σ=1.5, per-channel
  mean), implemented locally so the number is reproducible without extra
  dependencies.
* ``lpips`` — LPIPS perceptual distance (Zhang et al., CVPR 2018). Only measured
  when the ``lpips`` package *and* its torchvision trunk weights are available;
  otherwise the field is ``null`` with an explicit ``lpipsStatus`` reason. The
  number is never estimated or faked.
* ``identitySimilarity`` — cosine similarity between a transient SFace embedding
  of the original crop and of the derivative (OpenCV Zoo
  ``face_recognition_sface_2021dec.onnx``, MIT). Embeddings are computed here,
  compared once and discarded: nothing is stored, enrolled or compared against
  any gallery. Requires a detectable face in the original.
* ``utility`` — face detectability before/after (YuNet 2023mar, MIT): detection
  score and inter-eye distance in pixels.

``evaluate`` returns a plain dict shaped for the derivative record's ``harness``
block. ``HarnessBounds`` decides pass/fail; anything out of bounds is reported in
``failedBounds`` and tier-1 (learned) artifacts that fail are refused outright.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import importlib
import math
import os
import sys
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

from enhance import EnhancementError

HARNESS_VERSION = "1.0.0"

# Known-absence reasons, so a null metric is never ambiguous.
STATUS_MEASURED = "measured"
STATUS_NOT_EVALUATED = "not_evaluated"
STATUS_NO_FACE_ORIGINAL = "no-face-detected-in-original"
STATUS_NO_FACE_DERIVATIVE = "no-face-detected-in-derivative"
STATUS_LPIPS_UNAVAILABLE = "lpips-unavailable"
STATUS_IDENTITY_BACKEND_MISSING = "identity-backend-unavailable"


class HarnessError(EnhancementError):
    code = "harness_error"


class HarnessBackendUnavailable(HarnessError):
    code = "harness_backend_unavailable"


class HarnessBoundExceeded(HarnessError):
    code = "harness_bound_exceeded"


# ---------------------------------------------------------------------------
# Reference metrics
# ---------------------------------------------------------------------------


def psnr_db(original: np.ndarray, derivative: np.ndarray, *, peak: float = 255.0) -> float:
    """PSNR in dB between two same-shaped 8-bit images."""
    _require_same_shape(original, derivative)
    left = original.astype(np.float64)
    right = derivative.astype(np.float64)
    mse = float(np.mean((left - right) ** 2))
    if mse <= 0.0:
        return float("inf")
    return float(10.0 * np.log10((peak ** 2) / mse))


def _require_same_shape(original: np.ndarray, derivative: np.ndarray) -> None:
    if not isinstance(original, np.ndarray) or not isinstance(derivative, np.ndarray):
        raise HarnessError("Harness metrics require numpy arrays")
    if original.shape != derivative.shape:
        raise HarnessError(f"Shape mismatch: original {original.shape} vs derivative {derivative.shape}")


def ssim(original: np.ndarray, derivative: np.ndarray) -> float:
    """Mean SSIM over channels (Wang et al. 2004, Gaussian 11×11 σ=1.5)."""
    _require_same_shape(original, derivative)
    values: list[float] = []
    for channel in range(original.shape[2]):
        left = original[:, :, channel].astype(np.float64)
        right = derivative[:, :, channel].astype(np.float64)
        mu_left = cv2.GaussianBlur(left, (11, 11), 1.5)
        mu_right = cv2.GaussianBlur(right, (11, 11), 1.5)
        mu_left_sq = mu_left * mu_left
        mu_right_sq = mu_right * mu_right
        mu_product = mu_left * mu_right
        sigma_left = cv2.GaussianBlur(left * left, (11, 11), 1.5) - mu_left_sq
        sigma_right = cv2.GaussianBlur(right * right, (11, 11), 1.5) - mu_right_sq
        sigma_product = cv2.GaussianBlur(left * right, (11, 11), 1.5) - mu_product
        c1 = (0.01 * 255.0) ** 2
        c2 = (0.03 * 255.0) ** 2
        numerator = (2.0 * mu_product + c1) * (2.0 * sigma_product + c2)
        denominator = (mu_left_sq + mu_right_sq + c1) * (sigma_left + sigma_right + c2)
        values.append(float(np.mean(numerator / denominator)))
    return float(np.mean(values))


# ---------------------------------------------------------------------------
# LPIPS (optional backend)
# ---------------------------------------------------------------------------


class LpipsMetric:
    """LPIPS perceptual distance with an explicit availability status.

    The official LPIPS linear calibration (shipped with the package under
    ``weights/v0.1/``) is combined with the official AlexNet ImageNet trunk. The
    trunk comes from the local torchvision cache: ``download.pytorch.org``
    answered HTTP 403 for both AlexNet filenames from this host (2026-09-29), so
    the trunk is loaded from the *legacy-format* checkpoint already present in
    ``~/.cache/torch/hub/checkpoints`` and verified (size, SHA-256, strict
    state-dict load) before use. ``trunkProvenance`` in the status block records
    exactly which file was used, so the number is reproducible or refutable.
    """

    MODERN_CHECKPOINT = "alexnet-owt-7f6fbcc9.pth"
    LEGACY_CHECKPOINT = "alexnet-owt-7be5be79.pth"
    CHECKPOINT_URL = "https://download.pytorch.org/models/"

    def __init__(
        self,
        search_paths: Sequence[str | Path] = (),
        net: str = "alex",
        trunk_checkpoint: str | Path | None = None,
    ):
        self._net_name = net
        self._search_paths = [str(path) for path in search_paths]
        self._trunk_checkpoint = Path(trunk_checkpoint) if trunk_checkpoint is not None else None
        self._lock = threading.Lock()
        self._model: Any = None
        self._status: str = STATUS_NOT_EVALUATED
        self._detail: str | None = None
        self._trunk_provenance: dict[str, Any] | None = None

    def _import(self) -> Any:
        for path in reversed(self._search_paths):
            if path and path not in sys.path and Path(path).exists():
                sys.path.insert(0, path)
        return importlib.import_module("lpips")

    @property
    def status(self) -> str:
        return self._status

    @property
    def detail(self) -> str | None:
        return self._detail

    @property
    def trunk_provenance(self) -> dict[str, Any] | None:
        return dict(self._trunk_provenance) if self._trunk_provenance is not None else None

    def available(self) -> bool:
        try:
            self._ensure_model()
        except Exception:
            return False
        return True

    def _candidate_trunks(self) -> list[Path]:
        if self._trunk_checkpoint is not None:
            return [self._trunk_checkpoint]
        cache = Path.home() / ".cache" / "torch" / "hub" / "checkpoints"
        return [cache / self.MODERN_CHECKPOINT, cache / self.LEGACY_CHECKPOINT]

    def _load_trunk(self, torch: Any, torchvision_models: Any) -> tuple[Any, dict[str, Any]]:
        errors: list[str] = []
        for candidate in self._candidate_trunks():
            if not candidate.exists() or candidate.stat().st_size < 100_000_000:
                errors.append(f"{candidate.name}: absent or implausibly small")
                continue
            digest = hashlib.sha256()
            with candidate.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            checksum = digest.hexdigest()
            try:
                state = torch.load(candidate, map_location="cpu", weights_only=True)
            except Exception as exc:  # corrupt / incompatible serialization
                errors.append(f"{candidate.name}: unreadable ({type(exc).__name__}: {exc})")
                continue
            if isinstance(state, Mapping) and "state_dict" in state:
                state = state["state_dict"]
            model = torchvision_models.alexnet(weights=None)
            try:
                missing, unexpected = model.load_state_dict(state, strict=False)
            except Exception as exc:
                errors.append(f"{candidate.name}: state_dict rejected ({type(exc).__name__}: {exc})")
                continue
            if missing or unexpected:
                errors.append(
                    f"{candidate.name}: incomplete state_dict (missing={len(missing)}, unexpected={len(unexpected)})"
                )
                continue
            model.eval()
            provenance = {
                "path": str(candidate),
                "sha256": checksum,
                "bytes": candidate.stat().st_size,
                "source": self.CHECKPOINT_URL + candidate.name,
                "format": "legacy" if candidate.name == self.LEGACY_CHECKPOINT else "current",
            }
            return model, provenance
        raise HarnessBackendUnavailable(
            "no usable AlexNet trunk in the local torchvision cache "
            f"(download.pytorch.org is blocked from this host: HTTP 403); tried: {errors}"
        )

    def _ensure_model(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                module = self._import()
            except ImportError as exc:
                self._status = STATUS_LPIPS_UNAVAILABLE
                self._detail = f"lpips package not importable: {exc}"
                raise HarnessBackendUnavailable(self._detail) from exc
            try:
                import torch
                import torchvision.models as torchvision_models
                import lpips.pretrained_networks as pretrained_networks
            except ImportError as exc:
                self._status = STATUS_LPIPS_UNAVAILABLE
                self._detail = f"torch/torchvision not importable: {exc}"
                raise HarnessBackendUnavailable(self._detail) from exc

            trunk, provenance = self._load_trunk(torch, torchvision_models)
            original_tv = pretrained_networks.tv
            try:
                # Point the package's trunk factory at the verified local weights,
                # then restore the module attribute immediately afterwards.
                pretrained_networks.tv = _TrunkShim(original_tv, trunk)
                self._model = module.LPIPS(net=self._net_name, verbose=False)
            except Exception as exc:
                self._status = STATUS_LPIPS_UNAVAILABLE
                self._detail = f"lpips construction failed ({type(exc).__name__}: {exc})"
                raise HarnessBackendUnavailable(self._detail) from exc
            finally:
                pretrained_networks.tv = original_tv
            self._model.eval()
            self._trunk_provenance = provenance
            self._self_check()
            self._status = STATUS_MEASURED
            self._detail = (
                f"lpips net={self._net_name}, trunk {Path(provenance['path']).name} "
                f"sha256={provenance['sha256'][:12]}…"
            )
            return self._model

    def _self_check(self) -> None:
        """A mis-loaded trunk silently produces garbage; refuse instead."""
        probe = (np.arange(64 * 64 * 3, dtype=np.uint8) % 251).reshape(64, 64, 3).copy()
        value = self._measure_raw(probe, probe.copy())
        if value is None or value > 1e-5:
            self._model = None
            raise HarnessBackendUnavailable(f"lpips self-check failed (identical pair -> {value}); trunk is unusable")

    def _to_tensor(self, image: np.ndarray) -> Any:
        import torch

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1).unsqueeze(0)
        return tensor * 2.0 - 1.0

    def _measure_raw(self, original: np.ndarray, derivative: np.ndarray) -> float | None:
        if self._model is None:
            return None
        import torch

        with torch.no_grad():
            value = self._model(self._to_tensor(original), self._to_tensor(derivative))
        return float(value.detach().cpu().reshape(-1)[0].item())

    def measure(self, original: np.ndarray, derivative: np.ndarray) -> float:
        _require_same_shape(original, derivative)
        self._ensure_model()
        value = self._measure_raw(original, derivative)
        if value is None:
            raise HarnessBackendUnavailable("lpips model not initialized")
        return float(value)

    def status_block(self) -> dict[str, Any]:
        return {
            "status": self._status,
            "detail": self._detail,
            "version": HARNESS_VERSION,
            "trunkProvenance": self.trunk_provenance,
        }


class _TrunkShim:
    """Proxy exposing the verified local AlexNet to lpips' trunk factory."""

    def __init__(self, real: Any, trunk: Any):
        self._real = real
        self._trunk = trunk

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)

    def alexnet(self, *args: Any, **kwargs: Any) -> Any:
        return self._trunk


# ---------------------------------------------------------------------------
# Face detection utility + transient identity similarity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaceObservation:
    score: float
    bbox: tuple[int, int, int, int]
    landmarks: tuple[tuple[float, float], ...]
    ied_px: float | None


def model_provenance(path: Path) -> dict[str, Any]:
    """{path, bytes, sha256} for a model file — so a report names its own model."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "bytes": Path(path).stat().st_size, "sha256": digest.hexdigest()}


class FaceProbe:
    """YuNet detection probe used for the utility measure (MIT, OpenCV Zoo)."""

    def __init__(self, model_path: str | Path, *, score_threshold: float = 0.5, input_size: int = 640):
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise HarnessBackendUnavailable(f"YuNet weights not found: {self.model_path}")
        self.score_threshold = float(score_threshold)
        self.input_size = int(input_size)
        self._lock = threading.Lock()
        self._detector: Any = None
        self._provenance: dict[str, Any] | None = None

    @property
    def provenance(self) -> dict[str, Any]:
        if self._provenance is None:
            self._provenance = {
                "name": "YuNet 2023mar (OpenCV Zoo)",
                "license": "MIT (OpenCV Zoo model directory)",
                **model_provenance(self.model_path),
            }
        return dict(self._provenance)

    def _ensure(self, frame_size: tuple[int, int]) -> Any:
        with self._lock:
            if self._detector is None:
                self._detector = cv2.FaceDetectorYN.create(
                    str(self.model_path), "", (self.input_size, self.input_size), self.score_threshold, 0.3, 5000
                )
            self._detector.setInputSize((int(frame_size[1]), int(frame_size[0])))
            return self._detector

    def detect(self, bgr: np.ndarray) -> FaceObservation | None:
        if bgr.ndim != 3 or bgr.shape[0] < 8 or bgr.shape[1] < 8:
            return None
        resized = bgr
        scale = 1.0
        longest = max(bgr.shape[0], bgr.shape[1])
        if longest > self.input_size:
            scale = self.input_size / float(longest)
            resized = cv2.resize(bgr, (max(8, int(round(bgr.shape[1] * scale))), max(8, int(round(bgr.shape[0] * scale)))))
        detector = self._ensure(resized.shape[:2])
        _, faces = detector.detect(resized)
        if faces is None or len(faces) == 0:
            return None
        faces = np.asarray(faces, dtype=np.float32)
        best = faces[int(np.argmax(faces[:, -1]))]
        inverse = 1.0 / scale if scale else 1.0
        x, y, width, height = (float(value) * inverse for value in best[:4])
        landmarks = tuple(
            (float(best[4 + index * 2]) * inverse, float(best[5 + index * 2]) * inverse) for index in range(5)
        )
        right_eye, left_eye = landmarks[0], landmarks[1]
        ied = float(np.hypot(left_eye[0] - right_eye[0], left_eye[1] - right_eye[1]))
        return FaceObservation(
            score=float(best[-1]),
            bbox=(int(round(x)), int(round(y)), int(round(x + width)), int(round(y + height))),
            landmarks=landmarks,
            ied_px=ied,
        )


class IdentitySimilarity:
    """Transient SFace embedding cosine between original and derivative.

    Policy: the embeddings live only inside :meth:`measure`. They are never
    returned, logged, stored, or compared to any registry — only the scalar
    cosine between the two crops of the same incident is reported.
    """

    def __init__(self, model_path: str | Path, probe: FaceProbe | None = None):
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise HarnessBackendUnavailable(f"SFace weights not found: {self.model_path}")
        self.probe = probe
        self._lock = threading.Lock()
        self._recognizer: Any = None
        self._provenance: dict[str, Any] | None = None

    @property
    def provenance(self) -> dict[str, Any]:
        if self._provenance is None:
            self._provenance = {
                "name": "SFace 2021dec (OpenCV Zoo)",
                "license": "MIT (OpenCV Zoo model directory)",
                **model_provenance(self.model_path),
            }
        return dict(self._provenance)

    def _ensure(self) -> Any:
        with self._lock:
            if self._recognizer is None:
                self._recognizer = cv2.FaceRecognizerSF.create(str(self.model_path), "")
            return self._recognizer

    def _embedding(self, recognizer: Any, crop: np.ndarray, observation: FaceObservation) -> np.ndarray:
        box = np.array([observation.bbox[0], observation.bbox[1], observation.bbox[2] - observation.bbox[0], observation.bbox[3] - observation.bbox[1]], dtype=np.float32)
        landmarks = np.array(observation.landmarks, dtype=np.float32).reshape(1, 10)
        aligned = recognizer.alignCrop(crop, np.hstack([box.reshape(1, 4), landmarks]))
        feature = recognizer.feature(aligned)
        return np.asarray(feature, dtype=np.float32).reshape(-1)

    def measure(self, original: np.ndarray, derivative: np.ndarray) -> tuple[float | None, str]:
        """Return (cosine similarity, status). Never returns an embedding."""
        if self.probe is None:
            return None, STATUS_IDENTITY_BACKEND_MISSING
        original_face = self.probe.detect(original)
        if original_face is None:
            return None, STATUS_NO_FACE_ORIGINAL
        derivative_face = self.probe.detect(derivative)
        if derivative_face is None:
            return None, STATUS_NO_FACE_DERIVATIVE
        recognizer = self._ensure()
        embedding_original = self._embedding(recognizer, original, original_face)
        embedding_derivative = self._embedding(recognizer, derivative, derivative_face)
        try:
            norm_original = float(np.linalg.norm(embedding_original))
            norm_derivative = float(np.linalg.norm(embedding_derivative))
            if norm_original == 0.0 or norm_derivative == 0.0:
                return None, STATUS_IDENTITY_BACKEND_MISSING
            cosine = float(np.dot(embedding_original, embedding_derivative) / (norm_original * norm_derivative))
        finally:
            del embedding_original, embedding_derivative
            original_face = derivative_face = None
        return cosine, STATUS_MEASURED


# ---------------------------------------------------------------------------
# Bounds and report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HarnessBounds:
    """Pass/fail bounds for derivative artifacts.

    Defaults are the tier-0 operating point calibrated on the synthetic
    distortion fixtures in ``docs/campaign/experiments/`` (see the EXP cards for
    measured values). Tier-1 must additionally clear ``min_identity_similarity``
    and ``min_lpips_required`` (LPIPS must be *measurable*, otherwise learned
    enhancement is refused).
    """

    min_psnr_db: float = 14.0
    min_ssim: float = 0.60
    max_lpips: float = 0.55
    min_identity_similarity: float = 0.90
    require_lpips: bool = False
    require_identity_when_face: bool = True
    require_face_preserved: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "minPsnrDb": self.min_psnr_db,
            "minSsim": self.min_ssim,
            "maxLpips": self.max_lpips,
            "minIdentitySimilarity": self.min_identity_similarity,
            "requireLpips": self.require_lpips,
            "requireIdentityWhenFace": self.require_identity_when_face,
            "requireFacePreserved": self.require_face_preserved,
        }


def default_bounds(tier: int) -> HarnessBounds:
    """Tier-0 keeps the deterministic envelope; tier-1 demands the full gate."""
    if tier >= 1:
        return HarnessBounds(
            min_psnr_db=20.0,
            min_ssim=0.70,
            max_lpips=0.35,
            min_identity_similarity=0.92,
            require_lpips=True,
            require_identity_when_face=True,
            require_face_preserved=True,
        )
    return HarnessBounds()


@dataclass
class HarnessReport:
    """The ``harness`` block stored on every derivative record."""

    status: str = STATUS_NOT_EVALUATED
    passed: bool | None = None
    psnr_db: float | None = None
    ssim: float | None = None
    lpips: float | None = None
    identity_similarity: float | None = None
    face_score_before: float | None = None
    face_score_after: float | None = None
    ied_before_px: float | None = None
    ied_after_px: float | None = None
    failed_bounds: list[str] = field(default_factory=list)
    identical_pixels: bool = False
    lpips_status: str = STATUS_NOT_EVALUATED
    lpips_detail: str | None = None
    lpips_trunk: dict[str, Any] | None = None
    identity_status: str = STATUS_NOT_EVALUATED
    identity_model: dict[str, Any] | None = None
    detector_model: dict[str, Any] | None = None
    utility_status: str = STATUS_NOT_EVALUATED
    bounds: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "passed": self.passed,
            "psnrDb": self.psnr_db,
            "ssim": self.ssim,
            "lpips": self.lpips,
            "identitySimilarity": self.identity_similarity,
            "utility": {
                "faceDetectScoreBefore": self.face_score_before,
                "faceDetectScoreAfter": self.face_score_after,
                "iedBeforePx": self.ied_before_px,
                "iedAfterPx": self.ied_after_px,
            },
            "failedBounds": list(self.failed_bounds),
            "identicalPixels": self.identical_pixels,
            "lpipsStatus": self.lpips_status,
            "lpipsDetail": self.lpips_detail,
            "lpipsTrunk": self.lpips_trunk,
            "identityStatus": self.identity_status,
            "identityModel": self.identity_model,
            "detectorModel": self.detector_model,
            "utilityStatus": self.utility_status,
            "bounds": dict(self.bounds),
            "notes": list(self.notes),
            "version": HARNESS_VERSION,
        }


def evaluate(
    original: np.ndarray,
    derivative: np.ndarray,
    *,
    bounds: HarnessBounds | None = None,
    probe: FaceProbe | None = None,
    identity: IdentitySimilarity | None = None,
    lpips_metric: LpipsMetric | None = None,
) -> dict[str, Any]:
    """Measure a derivative against its original and apply the bounds.

    Every number in the returned block is finite or ``null``: the ledger
    serializes records with ``allow_nan=False``, so an infinite PSNR (identical
    pixels) is recorded as ``null`` with an explicit note and the
    ``identicalPixels`` flag instead of breaking the chain write.
    """
    active_bounds = bounds or HarnessBounds()
    report = HarnessReport(bounds=active_bounds.as_dict())
    raw_psnr = psnr_db(original, derivative)
    if math.isfinite(raw_psnr):
        report.psnr_db = raw_psnr
    else:
        report.identical_pixels = True
        report.notes.append(
            "psnrDb is infinite because the derivative pixels are identical to the reference; recorded as null"
        )
    raw_ssim = ssim(original, derivative)
    if math.isfinite(raw_ssim):
        report.ssim = raw_ssim
    else:
        report.notes.append("ssim was not finite; recorded as null")

    if lpips_metric is not None:
        if lpips_metric.available():
            try:
                report.lpips = lpips_metric.measure(original, derivative)
                report.lpips_status = STATUS_MEASURED
                report.lpips_detail = lpips_metric.detail
                report.lpips_trunk = lpips_metric.trunk_provenance
            except Exception as exc:
                report.lpips_status = STATUS_LPIPS_UNAVAILABLE
                report.notes.append(f"lpips measurement failed: {type(exc).__name__}: {exc}")
        else:
            report.lpips_status = STATUS_LPIPS_UNAVAILABLE
            report.notes.append(lpips_metric.detail or "lpips backend unavailable")
    else:
        report.lpips_status = STATUS_LPIPS_UNAVAILABLE
        report.notes.append("no lpips backend configured for this run")

    if probe is not None:
        report.detector_model = probe.provenance
    if identity is not None:
        report.identity_model = identity.provenance

    face_original = probe.detect(original) if probe is not None else None
    face_derivative = probe.detect(derivative) if probe is not None else None
    if probe is None:
        report.utility_status = STATUS_NOT_EVALUATED
    elif face_original is None:
        report.utility_status = STATUS_NO_FACE_ORIGINAL
    else:
        report.utility_status = STATUS_MEASURED
        report.face_score_before = face_original.score
        report.ied_before_px = face_original.ied_px
        report.face_score_after = face_derivative.score if face_derivative is not None else None
        report.ied_after_px = face_derivative.ied_px if face_derivative is not None else None

    if identity is not None:
        cosine, status = identity.measure(original, derivative)
        report.identity_similarity = cosine
        report.identity_status = status
    else:
        report.identity_status = STATUS_IDENTITY_BACKEND_MISSING

    report.failed_bounds = _failed_bounds(report, active_bounds)
    report.status = STATUS_MEASURED
    report.passed = not report.failed_bounds
    return report.as_dict()


def _failed_bounds(report: HarnessReport, bounds: HarnessBounds) -> list[str]:
    failed: list[str] = []
    if report.psnr_db is not None and report.psnr_db < bounds.min_psnr_db:
        failed.append(f"psnrDb<{bounds.min_psnr_db}")
    if report.ssim is not None and report.ssim < bounds.min_ssim:
        failed.append(f"ssim<{bounds.min_ssim}")
    if report.lpips is not None and report.lpips > bounds.max_lpips:
        failed.append(f"lpips>{bounds.max_lpips}")
    if bounds.require_lpips and report.lpips is None:
        failed.append("lpips-not-measurable")
    if report.identity_similarity is not None and report.identity_similarity < bounds.min_identity_similarity:
        failed.append(f"identitySimilarity<{bounds.min_identity_similarity}")
    if bounds.require_identity_when_face and report.utility_status == STATUS_MEASURED and report.identity_similarity is None:
        failed.append(f"identity-not-measurable({report.identity_status})")
    if bounds.require_face_preserved and report.utility_status == STATUS_MEASURED and report.face_score_after is None:
        failed.append("face-lost-by-enhancement")
    return failed


def assert_within_bounds(report: Mapping[str, Any]) -> None:
    """Raise when a measured report failed, or was never measured."""
    if report.get("status") != STATUS_MEASURED:
        raise HarnessBoundExceeded(f"Harness report is not measured (status={report.get('status')!r})")
    if report.get("passed") is not True:
        raise HarnessBoundExceeded(f"Distortion bounds failed: {report.get('failedBounds')}")


def default_backends(
    *,
    assets_dir: str | Path | None = None,
    lpips_paths: Sequence[str | Path] = (),
) -> dict[str, Any]:
    """Build the harness backends from the untracked ``assets/`` directory.

    Missing backends are reported, never fatal: a missing YuNet/SFace disables
    that metric with an explicit status instead of silently dropping it.
    """
    assets = Path(assets_dir) if assets_dir is not None else Path(
        os.environ.get("SENTINEL_ENHANCE_ASSETS", Path(__file__).resolve().parents[1] / "assets")
    )
    probe: FaceProbe | None = None
    identity: IdentitySimilarity | None = None
    yunet = assets / "face_detection_yunet_2023mar.onnx"
    sface = assets / "face_recognition_sface_2021dec.onnx"
    if yunet.exists():
        probe = FaceProbe(yunet)
        if sface.exists():
            identity = IdentitySimilarity(sface, probe=probe)
    paths = list(lpips_paths) or [assets / "pylibs"]
    return {
        "probe": probe,
        "identity": identity,
        "lpips_metric": LpipsMetric(paths),
        "assets_dir": str(assets),
    }
