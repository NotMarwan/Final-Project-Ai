"""Calibration artifact resolution, validation and the G-06 startup policy.

Artifact status semantics (honest three-state):
- ``unverified``: no usable artifact; scores are NOT probabilities.
- ``calibrated-candidate``: a schema-valid, held-out-evaluated candidate
  artifact is active (domain-limited; the artifact itself carries
  ``status: candidate-not-runtime-validated``).
- ``calibrated``: reserved for artifacts explicitly promoted to runtime
  validation (not produced by ``bench/calibrate.py``).

G-06 startup policy: the pipeline refuses to start without a valid artifact.
The ONLY escape hatch is the explicit development override
``AI_SENTINEL_CALIBRATION_UNVERIFIED_OVERRIDE=I-UNDERSTAND-SCORES-ARE-UNVERIFIED``
(an exact env phrase, logged at CRITICAL), and it is REFUSED when
``AI_SENTINEL_ENV`` is a production value. There is no config-file key that can
enable it, so it cannot be enabled silently from configuration.
"""
from __future__ import annotations

import json
import hashlib
from functools import lru_cache
import logging
import math
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CALIBRATION_OVERRIDE_ENV = "AI_SENTINEL_CALIBRATION_UNVERIFIED_OVERRIDE"
CALIBRATION_OVERRIDE_PHRASE = "I-UNDERSTAND-SCORES-ARE-UNVERIFIED"
PRODUCTION_ENV = "AI_SENTINEL_ENV"
PRODUCTION_VALUES = frozenset({"production", "prod"})

STATUS_UNVERIFIED = "unverified"
STATUS_CANDIDATE = "calibrated-candidate"
STATUS_CALIBRATED = "calibrated"

_HASH = re.compile(r"^[a-f0-9]{64}$")
_CACHE_TTL_SECONDS = 5.0  # g05-allow: cache freshness, not a decision threshold
_BANNER_WIDTH = 72  # g05-allow: log banner width, display only
_CACHE: dict[Any, tuple[float, dict[str, Any]]] = {}


class CalibrationArtifactError(RuntimeError):
    """Raised when calibration is required but missing, invalid or unverifiable."""


def resolve_calibration_path(raw_path: str | None = None, base_dir: Path | None = None) -> Path:
    root = base_dir or Path(__file__).resolve().parent
    candidate = raw_path or os.getenv("MODEL_CALIBRATION_PATH", "model_calibration.json")
    path = Path(candidate)
    return path if path.is_absolute() else (root / path)


def resolve_model_path(model_path: str | Path | None = None, base_dir: Path | None = None) -> Path:
    root = base_dir or Path(__file__).resolve().parent
    path = Path(model_path or os.getenv("WEIGHTS_PATH", "best_model.pt"))
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _file_identity(path: Path) -> tuple:
    try:
        stat = path.stat()
        return str(path.resolve()), stat.st_size, stat.st_mtime_ns
    except OSError:
        return str(path.resolve()), None, None


@lru_cache(maxsize=16)  # g05-allow: bounded checkpoint hash cache, not a model threshold

def _model_digest(identity: tuple) -> str:
    path, _size, _modified = identity
    with Path(path).open("rb") as handle:
        result = hashlib.file_digest(handle, "sha256").hexdigest()
    if _file_identity(Path(path)) != identity:
        raise CalibrationArtifactError("Checkpoint changed during calibration verification")
    return result


def _validate_model_binding(payload: dict[str, Any], model_path: Path) -> None:
    try:
        actual = _model_digest(_file_identity(model_path))
    except OSError as exc:
        raise CalibrationArtifactError("Calibration checkpoint is unavailable") from exc
    if actual != payload["model_sha256"]:
        raise CalibrationArtifactError("Calibration artifact belongs to a different checkpoint")
    if payload.get("logitBias", 0.0) != 0.0:  # g05-allow: temperature-only artifacts cannot add an unfitted logit shift
        raise CalibrationArtifactError("Temperature calibration cannot include an additional logit bias")
    if type(payload.get("classIndex", 1)) is not int or payload.get("classIndex", 1) not in (0, 1):  # g05-allow: binary class index domain
        raise CalibrationArtifactError("Calibration class index must be binary zero or one")
    expected = {
        "VIOLENCE_LOGIT_TEMPERATURE": float(payload["temperature"]),
        "VIOLENCE_LOGIT_BIAS": float(payload.get("logitBias", 0.0)),  # g05-allow: artifact default is zero logit shift
        "VIOLENCE_CLASS_INDEX": int(payload.get("classIndex", 1)),  # g05-allow: binary model class index, not a policy threshold
    }
    for name, value in expected.items():
        if name in os.environ:
            try:
                matches = math.isclose(float(os.environ[name]), value)
            except ValueError:
                matches = False
            if not matches:
                raise CalibrationArtifactError("Runtime score override is incompatible with calibration artifact")


def _hash_ok(value: Any) -> bool:
    return bool(_HASH.fullmatch(str(value or "")))


def validate_calibration_artifact(payload: Any) -> dict[str, Any]:
    """Strict validation of a bench-produced calibration artifact."""
    if not isinstance(payload, dict):
        raise CalibrationArtifactError("Calibration artifact must be a JSON object")
    if payload.get("schema_version") != 1:  # g05-allow: schema gate, not a policy value
        raise CalibrationArtifactError("Unsupported calibration artifact schema version")
    if payload.get("method") != "binary-temperature-scaling":
        raise CalibrationArtifactError("Calibration artifact method must be binary-temperature-scaling")
    temperature = payload.get("temperature")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not math.isfinite(temperature):
        raise CalibrationArtifactError("Calibration temperature must be finite numeric data")
    if temperature <= 0:  # g05-allow: temperature is a positive divisor
        raise CalibrationArtifactError("Calibration temperature must be positive")
    if not _hash_ok(payload.get("model_sha256")):
        raise CalibrationArtifactError("Calibration artifact must bind a scored-model SHA-256")
    if not _hash_ok(payload.get("input_sha256")):
        raise CalibrationArtifactError("Calibration artifact must bind its labeled-input SHA-256")
    for key in ("calibration", "held_out_before", "held_out_after"):
        block = payload.get(key)
        if not isinstance(block, dict) or not isinstance(block.get("count"), int) or block["count"] <= 0:  # g05-allow: nonempty denominator
            raise CalibrationArtifactError(f"Calibration artifact is missing {key} metrics with a positive count")
        for metric in ("nll", "brier", "ece"):
            value = block.get(metric)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:  # g05-allow: metrics are non-negative
                raise CalibrationArtifactError(f"Calibration artifact {key}.{metric} must be finite and non-negative")
    limitations = payload.get("limitations")
    if not isinstance(limitations, list) or not limitations or not all(isinstance(item, str) and item for item in limitations):
        raise CalibrationArtifactError("Calibration artifact must declare nonempty limitations")
    status = payload.get("status")
    if not isinstance(status, str) or status not in {"candidate-not-runtime-validated", "runtime-validated"}:
        raise CalibrationArtifactError("Calibration artifact status must be candidate-not-runtime-validated or runtime-validated")
    return payload


def normalize_calibration_profile(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a validated artifact onto the runtime profile keys inference.py reads.

    The legacy runtime profile uses ``logitTemperature``; the bench artifact
    uses ``temperature`` (F-40 consumption contract).
    """
    if "temperature" in payload and "logitTemperature" not in payload:
        profile = {key: value for key, value in payload.items() if key != "temperature"}
        profile["logitTemperature"] = float(payload["temperature"])
        profile["calibration_status"] = (
            STATUS_CALIBRATED if payload.get("status") == "runtime-validated" else STATUS_CANDIDATE
        )
        profile["_artifact"] = payload
        return profile
    profile = dict(payload)
    profile["calibration_status"] = STATUS_UNVERIFIED
    return profile


def load_calibration_profile(raw_path: str | None = None, base_dir: Path | None = None,
                             model_path: str | Path | None = None) -> dict[str, Any]:
    """Lenient loader for the runtime (F-40).

    Missing file -> ``{}``. A present-but-invalid or corrupt file is logged
    loudly and also returns ``{}`` (no silent degradation).
    """
    path = resolve_calibration_path(raw_path=raw_path, base_dir=base_dir)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        logger.error("Calibration artifact at %s is unreadable (%s); continuing unverified", path, type(exc).__name__)
        return {}
    if not isinstance(payload, dict):
        logger.error("Calibration artifact at %s is not a JSON object; continuing unverified", path)
        return {}
    if payload.get("schema_version") is not None:
        try:
            validate_calibration_artifact(payload)
            _validate_model_binding(payload, resolve_model_path(model_path, base_dir))
        except CalibrationArtifactError as exc:
            logger.error("Calibration artifact at %s is invalid (%s); continuing unverified", path, exc)
            return {}
        return normalize_calibration_profile(payload)
    # Legacy tuning files may contain score transforms, but cannot self-assert
    # calibration without the validated artifact and checkpoint binding above.
    return {**payload, "calibration_status": STATUS_UNVERIFIED}


def calibration_state(base_dir: Path | None = None, raw_path: str | None = None,
                      use_cache: bool = True, model_path: str | Path | None = None) -> dict[str, Any]:
    """Truthful calibration state for payloads and health surfaces."""
    path = resolve_calibration_path(raw_path=raw_path, base_dir=base_dir)
    active_model = resolve_model_path(model_path, base_dir)
    key = (_file_identity(path), _file_identity(active_model),
           tuple(os.getenv(name) for name in ("VIOLENCE_LOGIT_TEMPERATURE", "VIOLENCE_LOGIT_BIAS", "VIOLENCE_CLASS_INDEX")))
    now = time.monotonic()
    if use_cache and key in _CACHE:
        stamped, cached = _CACHE[key]
        if now - stamped < _CACHE_TTL_SECONDS:
            return dict(cached)
    profile = load_calibration_profile(raw_path=raw_path, base_dir=base_dir, model_path=active_model)
    status = profile.get("calibration_status", STATUS_UNVERIFIED)
    state = {
        "status": status,
        "artifact_path": str(path) if profile else None,
        "artifact_status": (profile.get("_artifact") or {}).get("status"),
        "temperature": float(profile.get("logitTemperature", 0.0)) or None,  # g05-allow: 0.0 marks "absent"
        "calibrated": status in {STATUS_CANDIDATE, STATUS_CALIBRATED},
        "dev_override": False,
    }
    if use_cache:
        _CACHE[key] = (now, state)
    return dict(state)


def enforce_startup_calibration(base_dir: Path | None = None, *, env: dict | None = None,
                                production: bool | None = None, raw_path: str | None = None) -> dict[str, Any]:
    """G-06: refuse to start without a calibration artifact (or a loud dev override)."""
    environment = dict(os.environ) if env is None else dict(env)
    state = calibration_state(base_dir=base_dir, raw_path=raw_path)
    if state["calibrated"]:
        logger.info("Calibration artifact active (%s); scores are reported as the artifact's calibrated quantity",
                    state["status"])
        return state
    is_production = (production if production is not None
                     else str(environment.get(PRODUCTION_ENV, "")).strip().lower() in PRODUCTION_VALUES)
    override = str(environment.get(CALIBRATION_OVERRIDE_ENV, ""))
    if override == CALIBRATION_OVERRIDE_PHRASE and not is_production:
        logger.critical(
            "\n%s\n"
            "  G-06 DEVELOPMENT OVERRIDE ACTIVE — NO CALIBRATION ARTIFACT.\n"
            "  Model scores are UNVERIFIED and MUST NOT be presented as calibrated probabilities.\n"
            "  artifact path checked: %s\n"
            "  to disable: unset %s\n%s",
            "=" * _BANNER_WIDTH, state["artifact_path"] or "(absent)", CALIBRATION_OVERRIDE_ENV, "=" * _BANNER_WIDTH,
        )
        state["dev_override"] = True
        return state
    reason = ("the development override is refused in production" if is_production
              else "no override is set")
    raise CalibrationArtifactError(
        "Refusing to start: no valid calibration artifact at "
        f"{state['artifact_path'] or resolve_calibration_path(base_dir=base_dir)} and {reason}. "
        f"Produce one with bench/calibrate.py from independently labeled held-out scores, or (development only) set "
        f"{CALIBRATION_OVERRIDE_ENV}={CALIBRATION_OVERRIDE_PHRASE}. "
        f"Production environments ({PRODUCTION_ENV} in {sorted(PRODUCTION_VALUES)}) can never enable the override."
    )
