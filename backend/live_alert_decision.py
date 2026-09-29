"""Temporal confirmation of model scores, with explicit observation identity.

Scores are not claimed to be calibrated unless a validated calibration artifact
is active; every response labels which quantity it carries (`model_score` vs
`calibrated_probability` vs `severity`). Every distinct observation, including
benign observations during cooldown, contributes to the bounded history.
"""
from __future__ import annotations

from enum import Enum
import math
import threading
import time
from typing import Any, Optional

try:
    from .decision_config import DecisionConfig, load_decision_config
    from .calibration_utils import calibration_state as resolve_calibration_state
except ImportError:
    from decision_config import DecisionConfig, load_decision_config
    from calibration_utils import calibration_state as resolve_calibration_state

_MS_PER_SECOND = 1000.0  # g05-allow: unit conversion, not a policy value
_ROUNDING_DIGITS = 2  # g05-allow: display rounding, not a policy value
_UNSET_CALIBRATED_VALUE = object()


class AlertState(str, Enum):
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    CONFIRMED_VIOLENCE = "CONFIRMED_VIOLENCE"
    COOLDOWN = "COOLDOWN"


class LiveAlertDecisionLayer:
    def __init__(
        self,
        watch_threshold: Optional[float] = None,
        confirm_threshold: Optional[float] = None,
        confirm_n: Optional[int] = None,
        confirm_m: Optional[int] = None,
        min_decision_interval_seconds: Optional[float] = None,
        cooldown_seconds: Optional[float] = None,
        base_model_threshold: Optional[float] = None,
        *,
        config: Optional[DecisionConfig] = None,
        history_max_age_seconds: Optional[float] = None,
        calibration_state: Optional[dict] = None,
    ):
        policy = config or load_decision_config()
        overrides = {
            "watch_threshold": watch_threshold,
            "confirm_threshold": confirm_threshold,
            "confirm_n": confirm_n,
            "confirm_m": confirm_m,
            "min_decision_interval_seconds": min_decision_interval_seconds,
            "cooldown_seconds": cooldown_seconds,
            "violence_threshold": base_model_threshold,
            "history_max_age_seconds": history_max_age_seconds,
        }
        self._lock = threading.RLock()
        self.config = policy.with_updates(**{k: v for k, v in overrides.items() if v is not None})
        self._calibration = (dict(calibration_state) if calibration_state is not None
                             else resolve_calibration_state(use_cache=True))
        self.reset()

    def __getattr__(self, name: str) -> Any:
        # Preserve the existing public policy attributes without duplicate state.
        if name == "base_model_threshold":
            return self.config.violence_threshold
        if name in DecisionConfig.__dataclass_fields__:
            return getattr(self.config, name)
        raise AttributeError(name)

    def apply_config(self, config: DecisionConfig) -> None:
        if not isinstance(config, DecisionConfig):
            raise TypeError("Expected validated DecisionConfig")
        with self._lock:
            if config != self.config:
                self.config = config
                # Votes under different operating policies must not be mixed.
                self.reset()

    def reset(self) -> None:
        with self._lock:
            self._state = AlertState.NORMAL
            self._rolling_history: list[tuple[float, float]] = []
            self._rolling_metadata: list[dict[str, Any]] = []
            self._cooldown_until = 0.0  # g05-allow: sentinel "no cooldown", not a threshold
            self._confirmed_alert = False
            self._last_decision_sample_time: Optional[float] = None
            self._last_probability: Optional[float] = None
            self._last_sample_id: Optional[int] = None
            self._last_decision_sample_accepted = False
            self._last_ignored_reason: Optional[str] = None
            self._clock_time: Optional[float] = None
            self._confirm_latency_ms: Optional[float] = None
            self._last_metadata: Optional[dict[str, Any]] = None

    @property
    def calibration_status(self) -> str:
        return str(self._calibration.get("status", "unverified"))

    @staticmethod
    def _time(value: Optional[float]) -> float:
        result = time.monotonic() if value is None else float(value)
        if not math.isfinite(result):
            raise ValueError("Decision timestamp must be finite")
        return result

    def _tick(self, now: float) -> float:
        # An out-of-order producer timestamp must never rewind cooldown time.
        now = max(now, self._clock_time) if self._clock_time is not None else now
        self._clock_time = now
        retained = [(sample, metadata) for sample, metadata in
                    zip(self._rolling_history, self._rolling_metadata)
                    if now - sample[0] <= self.history_max_age_seconds]  # g05-allow: sample tuple element 0 is its timestamp
        self._rolling_history = [sample for sample, _metadata in retained]
        self._rolling_metadata = [metadata for _sample, metadata in retained]
        if now < self._cooldown_until:
            self._state = AlertState.COOLDOWN
        elif not self._rolling_history:
            self._state = AlertState.NORMAL
        elif self._state in (AlertState.COOLDOWN, AlertState.CONFIRMED_VIOLENCE):
            self._state = (AlertState.WATCH if self._rolling_history[-1][1] >= self.watch_threshold  # g05-allow: last-element index
                           else AlertState.NORMAL)
        return now

    def update(
        self,
        calibrated_probability: float,
        sample_time: Optional[float] = None,
        *,
        sample_id: Optional[int] = None,
        current_time: Optional[float] = None,
        calibrated_value: Any = _UNSET_CALIBRATED_VALUE,
        raw_model_score: Optional[float] = None,
        score_source: str = "unknown",
        score_calibration_status: Optional[str] = None,
    ) -> dict[str, Any]:
        """Consume a unique producer observation; confirmed_alert is one event.

        sample_time and current_time share a monotonic clock. Explicit sequence
        IDs bypass the legacy interval heuristic: new benign windows cannot be
        discarded merely because they arrived quickly. Repeated/stale sequences
        never vote, even after a long render pause.
        """
        timestamp = self._time(sample_time)
        now = timestamp if current_time is None else self._time(current_time)
        probability = float(calibrated_probability)
        if not math.isfinite(probability) or not 0 <= probability <= 1:  # g05-allow: probability domain
            raise ValueError("Model score must be finite and between zero and one")
        if calibrated_value is _UNSET_CALIBRATED_VALUE:
            calibrated = (probability if self.calibration_status in {"calibrated", "calibrated-candidate"}
                          else None)
        elif calibrated_value is None:
            calibrated = None
        else:
            calibrated = float(calibrated_value)
            if not math.isfinite(calibrated) or not 0 <= calibrated <= 1:  # g05-allow: calibrated probability domain
                raise ValueError("Calibrated value must be finite and between zero and one")
        raw_score = None if raw_model_score is None else float(raw_model_score)
        if raw_score is not None and (not math.isfinite(raw_score) or not 0 <= raw_score <= 1):  # g05-allow: raw model score domain
            raise ValueError("Raw model score must be finite and between zero and one")
        score_status = str(score_calibration_status or
                           (self.calibration_status if calibrated is not None else "unverified"))
        if (calibrated is None or
                score_status not in {"calibrated", "calibrated-candidate"}):
            calibrated = None
            score_status = "unverified"
        metadata = {
            "raw_model_score": raw_score,
            "score_source": str(score_source or "unknown"),
            "calibrated_probability": calibrated,
            "calibration_status": score_status,
        }
        if sample_id is not None and (type(sample_id) is not int or sample_id < 0):  # g05-allow: sequence domain
            raise ValueError("Observation sequence must be a nonnegative integer")
        with self._lock:
            self._confirmed_alert = False
            now = self._tick(now)
            reason = None
            if timestamp > now:
                reason = "future_observation"
            elif sample_id is not None and self._last_sample_id is not None and sample_id <= self._last_sample_id:
                reason = "stale_sequence"
            elif (self._last_decision_sample_time is not None
                  and (timestamp < self._last_decision_sample_time
                       or (sample_id is None and timestamp == self._last_decision_sample_time))):
                reason = "out_of_order_timestamp"
            elif now - timestamp > self.history_max_age_seconds:
                reason = "expired_observation"
            elif (sample_id is None and self._last_decision_sample_time is not None
                  and timestamp - self._last_decision_sample_time < self.min_decision_interval_seconds):
                reason = "duplicate_or_too_soon"
            self._last_decision_sample_accepted = reason is None
            self._last_ignored_reason = reason
            if reason is not None:
                return self._build_response(now)

            self._last_decision_sample_time = timestamp
            self._last_probability = probability
            self._last_metadata = metadata
            if sample_id is not None:
                self._last_sample_id = sample_id
            self._rolling_history.append((timestamp, probability))
            self._rolling_metadata.append(metadata)
            self._rolling_history = self._rolling_history[-self.confirm_m:]
            self._rolling_metadata = self._rolling_metadata[-self.confirm_m:]

            if now < self._cooldown_until:
                self._state = AlertState.COOLDOWN
            elif probability < self.watch_threshold:
                self._state = AlertState.NORMAL
            elif self._check_confirmation_rule():
                self._state = AlertState.CONFIRMED_VIOLENCE
                self._confirmed_alert = True
                self._cooldown_until = now + self.cooldown_seconds
                self._confirm_latency_ms = max(0.0, (now - self._rolling_history[0][0]) * _MS_PER_SECOND)  # g05-allow: oldest-vote index and ms scaling
            else:
                self._state = AlertState.WATCH
            return self._build_response(now)

    def _vote_weight(self, probability: float) -> float:
        """Confidence weight of one qualifying vote (R5).

        At the default ``confirm_weight_gain`` of 0.0 every qualifying vote
        weighs 1.0, so the weighted rule collapses to the classic count rule.
        """
        span = 1.0 - self.confirm_threshold  # g05-allow: normalisation span, not a threshold
        if span <= 0:  # g05-allow: degenerate span guard
            return 1.0  # g05-allow: unit weight baseline
        bonus = max(0.0, probability - self.confirm_threshold) / span  # g05-allow: relative excess, [0,1]
        return 1.0 + self.confirm_weight_gain * bonus  # g05-allow: unit weight baseline

    def _check_confirmation_rule(self) -> bool:
        qualifying = [p for _, p in self._rolling_history if p >= self.confirm_threshold]
        if len(qualifying) < self.confirm_n:
            return False
        weight_sum = sum(self._vote_weight(p) for p in qualifying)
        if weight_sum < self.confirm_weight_sum:
            return False
        if self.cascade_gate_threshold > 0 and max(qualifying) < self.cascade_gate_threshold:  # g05-allow: 0 disables the gate
            return False
        return True

    def _confidence_rule_text(self) -> str:
        base = f"at least {self.confirm_n} of last {self.confirm_m} windows >= {self.confirm_threshold}"
        if self.confirm_weight_gain > 0 or self.confirm_weight_sum > self.confirm_n:  # g05-allow: defaults disable weighting
            base += (f" with confidence weight sum >= {self.confirm_weight_sum} "
                     f"(gain {self.confirm_weight_gain})")
        if self.cascade_gate_threshold > 0:  # g05-allow: 0 disables the anchor gate
            base += f" and at least one vote >= {self.cascade_gate_threshold}"
        return base

    def _build_response(self, now: float) -> dict[str, Any]:
        last = self._last_probability
        metadata = self._last_metadata or {
            "raw_model_score": None,
            "score_source": "unknown",
            "calibrated_probability": None,
            "calibration_status": self.calibration_status,
        }
        calibrated = metadata["calibrated_probability"]
        return {
            "alert_state": self._state.value,
            "confirmed_alert": self._confirmed_alert,
            "confirm_rule": self._confidence_rule_text(),
            "confirm_weight_sum": self.confirm_weight_sum,
            "confirm_weight_gain": self.confirm_weight_gain,
            "cascade_gate_threshold": self.cascade_gate_threshold,
            "rolling_history": [{
                "timestamp": ts,
                "model_score": round(prob, 4),  # g05-allow: display rounding
                "decision_score": round(prob, 4),  # g05-allow: display rounding
                "raw_model_score": (None if item["raw_model_score"] is None
                                    else round(item["raw_model_score"], 4)),  # g05-allow: display rounding
                "score_source": item["score_source"],
                "calibrated_probability": (None if item["calibrated_probability"] is None
                                           else round(item["calibrated_probability"], 4)),  # g05-allow: display rounding
                "calibration_status": item["calibration_status"],
            } for (ts, prob), item in zip(self._rolling_history, self._rolling_metadata)],
            "rolling_window_count": len(self._rolling_history),
            "history_count": len(self._rolling_history),
            "cooldown_remaining_seconds": round(max(0.0, self._cooldown_until - now), _ROUNDING_DIGITS),  # g05-allow: clamp at zero plus display rounding
            "watch_threshold": self.watch_threshold,
            "confirm_threshold": self.confirm_threshold,
            "confirm_n": self.confirm_n,
            "confirm_m": self.confirm_m,
            "decision_sample_accepted": self._last_decision_sample_accepted,
            "ignored_reason": self._last_ignored_reason,
            "last_decision_sample_time": self._last_decision_sample_time,
            "last_sample_id": self._last_sample_id,
            "last_probability": last,
            "model_score": last,
            "decision_score": last,
            "raw_model_score": metadata["raw_model_score"],
            "score_source": metadata["score_source"],
            "calibrated_probability": calibrated,
            "score_semantics": {
                "model_score": "legacy alias of the decision score consumed by confirmation; see score_source",
                "decision_score": "source-specific score consumed by confirmation; it may be raw or transformed",
                "raw_model_score": "untransformed score from the selected producer, when supplied",
                "score_source": "producer whose score supplied the decision observation",
                "calibrated_probability": ("temperature-scaled probability for this observation's producer"
                                           if calibrated is not None else
                                           "null because this observation has no applicable calibration artifact"),
                "rolling_history_calibrated_probability": "per-observation producer-calibrated value; null when unavailable",
                "severity": "rule-based band of the fused score (not a probability)",
            },
            "decision_confirm_latency_ms": self._confirm_latency_ms,
            "decision_confirm_latency_clock": ("decision-monotonic window-open->confirmed on the sample clock; "
                                               "NOT glass-to-alert"),
            "min_decision_interval_seconds": self.min_decision_interval_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "base_model_threshold": self.base_model_threshold,
            "policy_source": "config/thresholds.toml",
            "calibration_status": metadata["calibration_status"],
            "calibration_artifact_status": self.calibration_status,
        }

    def status(self, current_time: Optional[float] = None) -> dict[str, Any]:
        with self._lock:
            # Explicit current_time advances the clock without creating a vote.
            # Omission is a read-only snapshot, including in timestamp-based tests.
            now = (self._clock_time if current_time is None
                   and self._clock_time is not None else self._time(current_time))
            if current_time is not None:
                self._confirmed_alert = False
                now = self._tick(now)
            return self._build_response(now)

    def get_state(self) -> AlertState:
        with self._lock:
            return self._state

    def is_confirmed(self) -> bool:
        return self.get_state() == AlertState.CONFIRMED_VIOLENCE

    def is_cooldown(self) -> bool:
        return self.get_state() == AlertState.COOLDOWN


def create_decision_layer() -> LiveAlertDecisionLayer:
    return LiveAlertDecisionLayer()
