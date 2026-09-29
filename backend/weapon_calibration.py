"""Score calibration consumption for the weapon path (F-40).

Loads a temperature-scaling artifact produced by `bench/calibrate.py` and
binds it to the scored model by SHA-256. An artifact whose `model_sha256`
does not match the loaded ONNX file is rejected — calibration is never
applied across model versions.

Honesty contract (bench/calibrate.py): a `candidate-not-runtime-validated`
artifact must NEVER surface as "calibrated". Only an artifact whose status
says validated may report a validated calibration status.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

# Status strings reported at the F-09 boundary (`calibrationStatus`).
STATUS_ABSENT = "absent"
STATUS_CANDIDATE = "candidate-not-runtime-validated"
STATUS_VALIDATED = "validated"
STATUS_MISMATCH_REJECTED = "mismatch-rejected"

_ARTIFACT_STATUSES = {"candidate-not-runtime-validated", "validated"}


class CalibrationError(ValueError):
    """Invalid or unbindable calibration artifact."""


@dataclass(frozen=True)
class CalibrationArtifact:
    temperature: float
    model_sha256: str
    status: str
    input_sha256: str | None = None
    held_out_before: Mapping[str, Any] | None = None
    held_out_after: Mapping[str, Any] | None = None

    @property
    def reported_status(self) -> str:
        """What the runtime may surface: candidates never claim validation."""
        return STATUS_VALIDATED if self.status == "validated" else STATUS_CANDIDATE


def calibrated_probability(score: float, temperature: float) -> float:
    """Binary temperature scaling — same math as bench/calibrate.scale."""
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise CalibrationError("score must be a finite probability in [0,1]")
    if not math.isfinite(temperature) or temperature <= 0:
        raise CalibrationError("temperature must be finite and positive")
    probability = min(1 - 1e-12, max(1e-12, float(score)))
    logit = (math.log(probability) - math.log1p(-probability)) / temperature
    if logit >= 0:
        return 1 / (1 + math.exp(-logit))
    exponent = math.exp(logit)
    return exponent / (1 + exponent)


def load_calibration_artifact(
    path: str | Path, *, expected_model_sha256: str | None = None
) -> CalibrationArtifact:
    """Load and validate a bench/calibrate.py artifact.

    When `expected_model_sha256` is given (the sha256 of the loaded ONNX
    file), an artifact bound to a different model is rejected.
    """
    raw = Path(path).read_bytes()
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CalibrationError("calibration artifact is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise CalibrationError("calibration artifact must be a JSON object")
    temperature = payload.get("temperature")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) \
            or not math.isfinite(temperature) or temperature <= 0:
        raise CalibrationError("calibration artifact needs a positive finite temperature")
    model_sha256 = str(payload.get("model_sha256", ""))
    if len(model_sha256) != 64:
        raise CalibrationError("calibration artifact needs a model_sha256")
    if expected_model_sha256 is not None and model_sha256 != expected_model_sha256:
        raise CalibrationError("calibration artifact is bound to a different model")
    status = str(payload.get("status", ""))
    if status not in _ARTIFACT_STATUSES:
        raise CalibrationError(f"unsupported calibration artifact status: {status!r}")
    return CalibrationArtifact(
        temperature=float(temperature),
        model_sha256=model_sha256,
        status=status,
        input_sha256=payload.get("input_sha256"),
        held_out_before=payload.get("held_out_before"),
        held_out_after=payload.get("held_out_after"),
    )


class WeaponScoreCalibration:
    """Runtime side of F-40: bind-verify once, then score-wise scaling."""

    def __init__(self, artifact: CalibrationArtifact | None, *, rejection: str | None = None):
        self._artifact = artifact
        self._rejection = rejection

    @classmethod
    def from_path(
        cls, path: str | Path | None, *, expected_model_sha256: str | None = None
    ) -> "WeaponScoreCalibration":
        """No path -> absent. Broken/mismatched artifact -> rejected, never silent."""
        if not path:
            return cls(None)
        try:
            artifact = load_calibration_artifact(
                path, expected_model_sha256=expected_model_sha256
            )
        except (CalibrationError, OSError) as exc:
            return cls(None, rejection=str(exc))
        return cls(artifact)

    @property
    def status(self) -> str:
        if self._artifact is not None:
            return self._artifact.reported_status
        return STATUS_MISMATCH_REJECTED if self._rejection else STATUS_ABSENT

    @property
    def rejection_reason(self) -> str | None:
        return self._rejection

    def apply(self, score: float) -> float | None:
        """Calibrated probability, or None while no valid artifact exists."""
        if self._artifact is None:
            return None
        return calibrated_probability(score, self._artifact.temperature)
