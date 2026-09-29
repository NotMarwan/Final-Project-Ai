"""Tier-1 (learned) enhancement: Real-ESRGAN x4, gated by the distortion harness.

Verdict per the WT-08 research catalog: super-resolution is a **human-review
perceptual aid**, never evidence of true detail (Blau & Michaeli, CVPR 2018;
PULSE, CVPR 2020; SWGIT §11 has no counterpart for generative enhancement).
Mechanically, therefore:

* the artifact is only published when :mod:`enhance_harness` measures it inside
  the tier-1 bounds (PSNR/SSIM/LPIPS **and** the transient identity-similarity
  bound) — a refusal is a first-class outcome, not an error to paper over;
* the record carries ``derivationBasis: "learned"``, the model name, version,
  weights SHA-256 and license, and the ``ENHANCED DERIVATIVE`` label;
* the original is preserved and the UI must show it first.

Architecture: RRDBNet (Wang et al., "Real-ESRGAN: Training Real-World Blind
Super-Resolution with Pure Synthetic Data", arXiv:2107.10833, ICCVW 2021),
implemented here directly from the published architecture; the published
``RealESRGAN_x4plus`` weights are BSD-3-Clause (xinntao/Real-ESRGAN LICENSE).
``strict=True`` loading is deliberate: it proves the local implementation matches
the published weights tensor-for-tensor instead of "probably working".
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from enhance import (
    CropRef,
    EnhancementError,
    EnhancementService,
    HASH_BASIS_FILE,
    Tier0Ops,
    crop_frame,
    sha256_file_bytes,
)

try:  # torch is optional for tier-0-only deployments
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError as exc:  # pragma: no cover - exercised only without torch
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: Exception | None = exc
else:
    _TORCH_IMPORT_ERROR = None

TIER1_MODULE_VERSION = "1.0.0"
REALESRGAN_LICENSE = "BSD-3-Clause (xinntao/Real-ESRGAN LICENSE)"
REALESRGAN_SOURCE = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"


class Tier1Error(EnhancementError):
    code = "tier1_error"


class Tier1BackendUnavailable(Tier1Error):
    code = "tier1_backend_unavailable"


class Tier1WeightsInvalid(Tier1Error):
    code = "tier1_weights_invalid"


class Tier1InputTooLarge(Tier1Error):
    code = "tier1_input_too_large"


class Tier1RefusedByHarness(Tier1Error):
    code = "tier1_refused_by_harness"


if nn is not None:  # pragma: no branch - only skipped when torch is absent

    class ResidualDenseBlock(nn.Module):
        """Dense block with a 0.2-scaled residual, exactly as published."""

        def __init__(self, num_feat: int = 64, num_grow_ch: int = 32):
            super().__init__()
            self.conv1 = nn.Conv2d(num_feat, num_grow_ch, 3, 1, 1)
            self.conv2 = nn.Conv2d(num_feat + num_grow_ch, num_grow_ch, 3, 1, 1)
            self.conv3 = nn.Conv2d(num_feat + 2 * num_grow_ch, num_grow_ch, 3, 1, 1)
            self.conv4 = nn.Conv2d(num_feat + 3 * num_grow_ch, num_grow_ch, 3, 1, 1)
            self.conv5 = nn.Conv2d(num_feat + 4 * num_grow_ch, num_feat, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

        def forward(self, x: Any) -> Any:
            x1 = self.lrelu(self.conv1(x))
            x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
            x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
            x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
            x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
            return x5 * 0.2 + x


    class RRDB(nn.Module):
        """Residual-in-Residual Dense Block (three RDBs, 0.2 residual scale)."""

        def __init__(self, num_feat: int, num_grow_ch: int = 32):
            super().__init__()
            self.rdb1 = ResidualDenseBlock(num_feat, num_grow_ch)
            self.rdb2 = ResidualDenseBlock(num_feat, num_grow_ch)
            self.rdb3 = ResidualDenseBlock(num_feat, num_grow_ch)

        def forward(self, x: Any) -> Any:
            out = self.rdb1(x)
            out = self.rdb2(out)
            out = self.rdb3(out)
            return out * 0.2 + x


    class RRDBNet(nn.Module):
        """RRDBNet generator (x4) with the published layer naming."""

        def __init__(
            self,
            num_in_ch: int = 3,
            num_out_ch: int = 3,
            num_feat: int = 64,
            num_block: int = 23,
            num_grow_ch: int = 32,
            scale: int = 4,
        ):
            super().__init__()
            self.scale = scale
            self.conv_first = nn.Conv2d(num_in_ch, num_feat, 3, 1, 1)
            self.body = nn.Sequential(*[RRDB(num_feat, num_grow_ch) for _ in range(num_block)])
            self.conv_body = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_up1 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_up2 = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_hr = nn.Conv2d(num_feat, num_feat, 3, 1, 1)
            self.conv_last = nn.Conv2d(num_feat, num_out_ch, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

        def forward(self, x: Any) -> Any:
            feat = self.conv_first(x)
            feat = feat + self.conv_body(self.body(feat))
            feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
            feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
            return self.conv_last(self.lrelu(self.conv_hr(feat)))


@dataclass(frozen=True)
class Tier1Result:
    image: np.ndarray
    device: str
    inference_ms: float
    input_shape: tuple[int, int, int]
    output_shape: tuple[int, int, int]
    scale: int


class RealEsrganEnhancer:
    """Deterministic-inference Real-ESRGAN x4 wrapper with recorded provenance."""

    def __init__(
        self,
        weights_path: str | Path,
        *,
        device: str = "auto",
        scale: int = 4,
        max_input_side: int = 1024,
        pad_multiple: int = 4,
    ):
        if torch is None:
            raise Tier1BackendUnavailable(f"torch is required for tier 1: {_TORCH_IMPORT_ERROR}")
        self.weights_path = Path(weights_path)
        if not self.weights_path.exists():
            raise Tier1BackendUnavailable(f"Real-ESRGAN weights not found: {self.weights_path}")
        self.scale = int(scale)
        self.max_input_side = int(max_input_side)
        self.pad_multiple = int(pad_multiple)
        self.device = self._resolve_device(device)
        self.model = RRDBNet(scale=self.scale)
        state = torch.load(self.weights_path, map_location="cpu", weights_only=True)
        if isinstance(state, Mapping) and "params_ema" in state:
            state = state["params_ema"]
        elif isinstance(state, Mapping) and "params" in state:
            state = state["params"]
        try:
            self.model.load_state_dict(state, strict=True)
        except Exception as exc:
            raise Tier1WeightsInvalid(
                f"Real-ESRGAN weights do not match the RRDBNet implementation: {type(exc).__name__}: {exc}"
            ) from exc
        self.model.eval()
        self.model.to(self.device)
        self._provenance = {
            "name": "real-esrgan",
            "version": "x4plus",
            "weightsSha256": sha256_file_bytes(self.weights_path),
            "license": REALESRGAN_LICENSE,
            "source": REALESRGAN_SOURCE,
            "architecture": "RRDBNet (arXiv:2107.10833)",
            "parameters": {"numFeat": 64, "numBlock": 23, "numGrowCh": 32, "scale": self.scale},
        }

    def _resolve_device(self, device: str) -> Any:
        if device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        resolved = torch.device(device)
        if resolved.type == "cuda" and not torch.cuda.is_available():
            raise Tier1BackendUnavailable("CUDA requested but unavailable")
        return resolved

    @property
    def provenance(self) -> dict[str, Any]:
        return dict(self._provenance)

    def model_block(self) -> dict[str, Any]:
        """The ``model`` block stored on a tier-1 derivative record."""
        return {
            "name": self._provenance["name"],
            "version": self._provenance["version"],
            "weightsSha256": self._provenance["weightsSha256"],
            "license": self._provenance["license"],
        }

    def enhance(self, bgr: np.ndarray) -> Tier1Result:
        if bgr.ndim != 3 or bgr.shape[2] != 3:
            raise Tier1Error("Tier-1 input must be a 3-channel BGR ndarray")
        height, width = bgr.shape[:2]
        if max(height, width) > self.max_input_side:
            raise Tier1InputTooLarge(
                f"Tier-1 input {width}x{height} exceeds max side {self.max_input_side}; crop first"
            )
        pad_h = (self.pad_multiple - height % self.pad_multiple) % self.pad_multiple
        pad_w = (self.pad_multiple - width % self.pad_multiple) % self.pad_multiple
        padded = cv2.copyMakeBorder(bgr, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT_101) if (pad_h or pad_w) else bgr
        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = torch.from_numpy(np.ascontiguousarray(rgb)).permute(2, 0, 1).unsqueeze(0).to(self.device)
        started = time.perf_counter()
        with torch.no_grad():
            output = self.model(tensor)
            if self.device.type == "cuda":
                torch.cuda.synchronize()
        inference_ms = (time.perf_counter() - started) * 1000.0
        array = output.squeeze(0).permute(1, 2, 0).clamp(0.0, 1.0).cpu().numpy()
        array = (array * 255.0 + 0.5).astype(np.uint8)
        array = array[: height * self.scale, : width * self.scale]
        bgr_out = np.ascontiguousarray(cv2.cvtColor(array, cv2.COLOR_RGB2BGR))
        return Tier1Result(
            image=bgr_out,
            device=str(self.device),
            inference_ms=inference_ms,
            input_shape=(height, width, 3),
            output_shape=(bgr_out.shape[0], bgr_out.shape[1], 3),
            scale=self.scale,
        )


REFERENCE_INTERPOLATIONS: tuple[tuple[str, int], ...] = (
    ("nearest", cv2.INTER_NEAREST),
    ("cubic", cv2.INTER_CUBIC),
    ("lanczos", cv2.INTER_LANCZOS4),
)


class Tier1Pipeline:
    """Run tier-1 only through the harness gate, then publish or refuse.

    Super-resolution changes resolution, so the distortion metrics need a
    same-size reference. Three *deterministic, non-generative* references are
    measured (nearest / cubic / Lanczos x4 upscales of the original crop) and the
    gate uses the reference **most favourable to the candidate** — otherwise a
    refusal could be an artifact of a poor comparator rather than of the model.
    The selection rule is deterministic (fewest failed bounds, then lowest LPIPS,
    then highest SSIM, then declaration order) and every reference's numbers are
    stored in the record, so the verdict can be re-derived without trusting this
    summary.
    """

    def __init__(
        self,
        enhancer: RealEsrganEnhancer,
        service: EnhancementService,
        *,
        probe: Any = None,
        identity: Any = None,
        lpips_metric: Any = None,
        bounds: Any = None,
    ):
        self.enhancer = enhancer
        self.service = service
        self.probe = probe
        self.identity = identity
        self.lpips_metric = lpips_metric
        self.bounds = bounds
        self._attempts = 0
        self._refusals = 0
        self._published = 0

    @property
    def stats(self) -> dict[str, int]:
        return {"attempts": self._attempts, "refused": self._refusals, "published": self._published}

    def deterministic_reference(self, original_crop: np.ndarray, interpolation: int) -> np.ndarray:
        return cv2.resize(
            original_crop,
            (original_crop.shape[1] * self.enhancer.scale, original_crop.shape[0] * self.enhancer.scale),
            interpolation=interpolation,
        )

    def measure_candidate(self, original_crop: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
        """Measure the candidate against every deterministic reference."""
        import enhance_harness as harness_module

        bounds = self.bounds if self.bounds is not None else harness_module.default_bounds(tier=1)
        per_reference: dict[str, dict[str, Any]] = {}
        for name, interpolation in REFERENCE_INTERPOLATIONS:
            reference = self.deterministic_reference(original_crop, interpolation)
            per_reference[name] = harness_module.evaluate(
                reference,
                candidate,
                bounds=bounds,
                probe=self.probe,
                identity=self.identity,
                lpips_metric=self.lpips_metric,
            )
        chosen, report = self._select_reference(per_reference, bounds)
        report["comparisonBaselineUsed"] = (
            f"{chosen} x{self.enhancer.scale} upscale of the original crop (deterministic, non-generative)"
        )
        report["comparisonBaselines"] = {
            name: {
                "psnrDb": entry["psnrDb"],
                "ssim": entry["ssim"],
                "lpips": entry["lpips"],
                "identitySimilarity": entry["identitySimilarity"],
                "passed": entry["passed"],
                "failedBounds": entry["failedBounds"],
            }
            for name, entry in per_reference.items()
        }
        return report

    @staticmethod
    def _select_reference(
        per_reference: Mapping[str, Mapping[str, Any]], bounds: Any
    ) -> tuple[str, dict[str, Any]]:
        order = {name: index for index, (name, _) in enumerate(REFERENCE_INTERPOLATIONS)}

        def sort_key(item: tuple[str, Mapping[str, Any]]) -> tuple[int, float, float, int]:
            name, entry = item
            return (
                len(entry.get("failedBounds") or []),
                float(entry["lpips"]) if entry.get("lpips") is not None else 99.0,
                -float(entry["ssim"]) if entry.get("ssim") is not None else 0.0,
                order.get(name, 99),
            )

        name, entry = min(per_reference.items(), key=sort_key)
        return name, dict(entry)

    def enhance_crop(
        self,
        crop: CropRef,
        frame: np.ndarray,
        *,
        parent_path: str | None = None,
        parent_sha256: str | None = None,
        parent_hash_basis: str = HASH_BASIS_FILE,
        parent_source: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Enhance, measure, gate, publish. Raises on refusal (nothing published)."""
        self._attempts += 1
        original_crop, _ = crop_frame(frame, crop.bbox_xyxy)
        result = self.enhancer.enhance(original_crop)
        report = self.measure_candidate(original_crop, result.image)
        report["tier1"] = {
            "device": result.device,
            "inferenceMs": result.inference_ms,
            "scale": result.scale,
            "inputShape": list(result.input_shape),
            "outputShape": list(result.output_shape),
            "gatedBeforePublish": True,
        }
        if report.get("passed") is not True:
            self._refusals += 1
            raise Tier1RefusedByHarness(
                f"tier-1 output refused by the distortion harness: {report.get('failedBounds')}"
            )
        published_crop = replace(
            crop,
            bbox_xyxy=(0, 0, result.image.shape[1], result.image.shape[0]),
            bbox_space="source",
            is_derivative=True,
            derivative_of=crop.crop_id,
        )
        operations = [
            {
                "name": "real_esrgan_x4",
                "params": {
                    "scale": result.scale,
                    "device": result.device,
                    "inferenceMs": round(result.inference_ms, 3),
                    "outputClamped": True,
                    "comparisonBaseline": report["comparisonBaselineUsed"],
                },
            }
        ]
        record = self.service.enhance(
            published_crop,
            result.image,
            ops=Tier0Ops(),
            parent_path=parent_path,
            parent_sha256=parent_sha256,
            parent_hash_basis=parent_hash_basis,
            parent_source=parent_source,
            tier=1,
            model=self.enhancer.model_block(),
            harness_report=report,
            operations_override=operations,
        )
        self._published += 1
        return record
