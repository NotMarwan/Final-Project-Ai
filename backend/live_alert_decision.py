"""
Live Alert Decision Layer for AI-Sentinel
==========================================
Implements a conservative temporal confirmation policy on top of model output
to reduce false positive alerts during live demos.

This module does NOT:
- Train or fine-tune any model
- Modify model weights
- Overwrite the promoted model
- Change the base model threshold (0.45)

It ONLY adds a temporal confirmation layer that requires multiple consecutive
high-probability windows before triggering a visible alert.
"""

import os
import time
from enum import Enum
from typing import Optional, Dict, Any, List


class AlertState(str, Enum):
    """Alert states for the live decision layer."""
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    CONFIRMED_VIOLENCE = "CONFIRMED_VIOLENCE"
    COOLDOWN = "COOLDOWN"


class LiveAlertDecisionLayer:
    """
    Conservative live alert decision layer that adds temporal confirmation
    on top of model output to reduce false positives.
    
    Uses a rolling window approach:
    - NORMAL: calibrated_probability < WATCH_THRESHOLD
    - WATCH: probability >= WATCH_THRESHOLD but confirmation rule not met
    - CONFIRMED_VIOLENCE: at least CONFIRM_N of last CONFIRM_M windows have prob >= CONFIRM_THRESHOLD
    - COOLDOWN: after confirmed alert, suppress new alerts for ALERT_COOLDOWN_SECONDS
    """
    
    def __init__(
        self,
        watch_threshold: Optional[float] = None,
        confirm_threshold: Optional[float] = None,
        confirm_n: Optional[int] = None,
        confirm_m: Optional[int] = None,
        min_decision_interval_seconds: Optional[float] = None,
        cooldown_seconds: Optional[float] = None,
        base_model_threshold: float = 0.45,
    ):
        """
        Initialize the live alert decision layer.
        
        All thresholds can be overridden via environment variables:
        - AI_SENTINEL_WATCH_THRESHOLD (default 0.45)
        - AI_SENTINEL_CONFIRM_THRESHOLD (default 0.65)
        - AI_SENTINEL_CONFIRM_N (default 2)
        - AI_SENTINEL_CONFIRM_M (default 3)
        - AI_SENTINEL_MIN_DECISION_INTERVAL_SECONDS (default 0.50)
        - AI_SENTINEL_ALERT_COOLDOWN_SECONDS (default 3.0)
        
        Args:
            watch_threshold: Threshold for WATCH state (default from env or 0.45)
            confirm_threshold: Threshold for confirmation rule (default from env or 0.65)
            confirm_n: Number of windows needed in confirm rule (default from env or 2)
            confirm_m: Window size for confirm rule (default from env or 3)
            min_decision_interval_seconds: Minimum time between accepted decision samples
            cooldown_seconds: Cooldown period after confirmed alert (default from env or 3.0)
            base_model_threshold: Base model threshold (kept at 0.45, not modified)
        """
        # Load from environment variables with defaults
        self.watch_threshold = watch_threshold if watch_threshold is not None \
            else float(os.getenv("AI_SENTINEL_WATCH_THRESHOLD", "0.35"))
        
        self.confirm_threshold = confirm_threshold if confirm_threshold is not None \
            else float(os.getenv("AI_SENTINEL_CONFIRM_THRESHOLD", "0.50"))
        
        self.confirm_n = confirm_n if confirm_n is not None \
            else int(os.getenv("AI_SENTINEL_CONFIRM_N", "1"))
        
        self.confirm_m = confirm_m if confirm_m is not None \
            else int(os.getenv("AI_SENTINEL_CONFIRM_M", "3"))

        self.min_decision_interval_seconds = (
            min_decision_interval_seconds if min_decision_interval_seconds is not None
            else float(os.getenv("AI_SENTINEL_MIN_DECISION_INTERVAL_SECONDS", "0.50"))
        )
        
        self.cooldown_seconds = cooldown_seconds if cooldown_seconds is not None \
            else float(os.getenv("AI_SENTINEL_ALERT_COOLDOWN_SECONDS", "3.0"))
        
        # Base model threshold - kept for reference, not modified
        self.base_model_threshold = base_model_threshold
        
        # Current alert state
        self._state = AlertState.NORMAL
        
        # Rolling history of recent probabilities (for confirm rule)
        # Stores tuples of (timestamp, calibrated_probability)
        self._rolling_history: List[tuple] = []
        
        # Cooldown tracking
        self._cooldown_until: float = 0.0
        
        # Confirmed alert flag
        self._confirmed_alert: bool = False
        
        # Track if we just entered cooldown (to avoid spam)
        self._just_confirmed: bool = False

        # Track accepted decision samples so repeated stale frame updates do not
        # count as multiple votes toward the confirmation rule.
        self._last_decision_sample_time: Optional[float] = None
        self._last_probability: Optional[float] = None
        self._last_decision_sample_accepted: bool = False
        self._last_ignored_reason: Optional[str] = None
        
        print(f"[LiveAlert] Initialized with watch_threshold={self.watch_threshold}, "
              f"confirm_threshold={self.confirm_threshold}, confirm_n={self.confirm_n}, "
              f"confirm_m={self.confirm_m}, min_interval={self.min_decision_interval_seconds}s, "
              f"cooldown={self.cooldown_seconds}s")
    
    def reset(self) -> None:
        """Reset the decision layer state."""
        self._state = AlertState.NORMAL
        self._rolling_history.clear()
        self._cooldown_until = 0.0
        self._confirmed_alert = False
        self._just_confirmed = False
        self._last_decision_sample_time = None
        self._last_probability = None
        self._last_decision_sample_accepted = False
        self._last_ignored_reason = None
        print("[LiveAlert] State reset to NORMAL")
    
    def update(self, calibrated_probability: float, sample_time: Optional[float] = None) -> Dict[str, Any]:
        """
        Update the alert state based on a new model prediction.
        
        Args:
            calibrated_probability: The calibrated probability from the model (0.0 to 1.0)
            sample_time: Optional explicit timestamp for the decision sample
            
        Returns:
            Dictionary with decision layer output fields
        """
        current_time = time.time() if sample_time is None else float(sample_time)

        if self._last_decision_sample_time is not None:
            elapsed = current_time - self._last_decision_sample_time
            if elapsed < self.min_decision_interval_seconds:
                self._last_decision_sample_accepted = False
                self._last_ignored_reason = "duplicate_or_too_soon"
                return self._build_response(
                    current_time=current_time,
                    decision_sample_accepted=False,
                    ignored_reason=self._last_ignored_reason,
                )

        self._last_decision_sample_time = current_time
        self._last_probability = calibrated_probability
        self._last_decision_sample_accepted = True
        self._last_ignored_reason = None

        # Add accepted decision sample to rolling history
        self._rolling_history.append((current_time, calibrated_probability))
        
        # Trim history to confirm_m windows (keep only recent entries)
        # We keep a bit more than confirm_m for debugging, but confirm rule only uses last confirm_m
        while len(self._rolling_history) > max(self.confirm_m + 10, 20):
            self._rolling_history.pop(0)
        
        # Check if we're in cooldown
        if current_time < self._cooldown_until:
            self._state = AlertState.COOLDOWN
            self._confirmed_alert = False
            return self._build_response(
                current_time=current_time,
                decision_sample_accepted=True,
                ignored_reason=None,
            )
        
        # If we just came out of cooldown, transition to appropriate state
        if self._state == AlertState.COOLDOWN and current_time >= self._cooldown_until:
            # Transition based on current probability
            if calibrated_probability < self.watch_threshold:
                self._state = AlertState.NORMAL
            else:
                self._state = AlertState.WATCH
        
        # State machine logic
        if calibrated_probability < self.watch_threshold:
            # Probability below watch threshold -> NORMAL
            self._state = AlertState.NORMAL
            self._confirmed_alert = False
            self._just_confirmed = False
            
        elif self._state == AlertState.NORMAL or self._state == AlertState.WATCH:
            # In NORMAL or WATCH state, check confirmation rule
            if self._check_confirmation_rule():
                # Confirmed violence!
                self._state = AlertState.CONFIRMED_VIOLENCE
                self._confirmed_alert = True
                self._just_confirmed = True
                self._cooldown_until = current_time + self.cooldown_seconds
            else:
                # Not confirmed yet -> WATCH
                self._state = AlertState.WATCH
                # If we were just confirmed, don't immediately reset confirmed_alert
                # This allows the API to see the confirmed_alert for one more cycle
                if not self._just_confirmed:
                    self._confirmed_alert = False
                else:
                    # Reset just_confirmed after one cycle
                    self._just_confirmed = False
                    
        elif self._state == AlertState.CONFIRMED_VIOLENCE:
            # Already confirmed, check if we should stay confirmed or go to cooldown
            if self._check_confirmation_rule():
                # Still meeting confirmation rule -> stay confirmed
                self._confirmed_alert = True
                self._just_confirmed = True
                self._cooldown_until = current_time + self.cooldown_seconds
            else:
                # No longer meeting confirmation rule
                # Enter cooldown if we just confirmed, otherwise go to WATCH
                if self._just_confirmed:
                    self._state = AlertState.COOLDOWN
                    self._confirmed_alert = False
                    self._just_confirmed = False
                    self._cooldown_until = current_time + self.cooldown_seconds
                else:
                    self._state = AlertState.WATCH
                    self._confirmed_alert = False
        
        return self._build_response(
            current_time=current_time,
            decision_sample_accepted=True,
            ignored_reason=None,
        )
    
    def _check_confirmation_rule(self) -> bool:
        """
        Check if the confirmation rule is met.
        
        Rule: At least CONFIRM_N of the last CONFIRM_M windows must have
              calibrated_probability >= CONFIRM_THRESHOLD
        
        Returns:
            True if confirmation rule is met, False otherwise
        """
        recent_entries = self._rolling_history[-min(self.confirm_m, len(self._rolling_history)):]

        if len(recent_entries) < self.confirm_n:
            return False

        # Count how many have probability >= confirm_threshold
        count = sum(1 for _, prob in recent_entries if prob >= self.confirm_threshold)
        
        return count >= self.confirm_n
    
    def _build_response(
        self,
        current_time: float,
        decision_sample_accepted: bool,
        ignored_reason: Optional[str],
    ) -> Dict[str, Any]:
        """
        Build the response dictionary with all required fields.
        
        Args:
            current_time: Current timestamp
            decision_sample_accepted: Whether this update became a new decision sample
            ignored_reason: Reason for ignoring a sample, if any
            
        Returns:
            Dictionary with all decision layer output fields
        """
        # Calculate cooldown remaining
        cooldown_remaining = max(0.0, self._cooldown_until - current_time)
        
        # Build confirm rule description
        confirm_rule = f"at least {self.confirm_n} of last {self.confirm_m} windows >= {self.confirm_threshold}"
        
        # Build rolling history for response (last 10 entries for brevity)
        rolling_history = [
            {"timestamp": ts, "calibrated_probability": round(prob, 4)}
            for ts, prob in self._rolling_history[-10:]
        ]
        
        return {
            "alert_state": self._state.value,
            "confirmed_alert": self._confirmed_alert,
            "confirm_rule": confirm_rule,
            "rolling_history": rolling_history,
            "rolling_window_count": min(len(self._rolling_history), self.confirm_m),
            "cooldown_remaining_seconds": round(cooldown_remaining, 2),
            "watch_threshold": self.watch_threshold,
            "confirm_threshold": self.confirm_threshold,
            "confirm_n": self.confirm_n,
            "confirm_m": self.confirm_m,
            "decision_sample_accepted": decision_sample_accepted,
            "ignored_reason": ignored_reason,
            "last_decision_sample_time": self._last_decision_sample_time,
            "min_decision_interval_seconds": self.min_decision_interval_seconds,
            "cooldown_seconds": self.cooldown_seconds,
        }

    def status(self, current_time: Optional[float] = None) -> Dict[str, Any]:
        """Return the latest decision-layer state without adding a new sample."""
        return self._build_response(
            current_time=time.time() if current_time is None else float(current_time),
            decision_sample_accepted=self._last_decision_sample_accepted,
            ignored_reason=self._last_ignored_reason,
        )
    
    def get_state(self) -> AlertState:
        """Get the current alert state."""
        return self._state
    
    def is_confirmed(self) -> bool:
        """Check if currently in confirmed violence state."""
        return self._state == AlertState.CONFIRMED_VIOLENCE
    
    def is_cooldown(self) -> bool:
        """Check if currently in cooldown."""
        return self._state == AlertState.COOLDOWN


# For backward compatibility / simple import
def create_decision_layer() -> LiveAlertDecisionLayer:
    """
    Factory function to create a LiveAlertDecisionLayer with environment-based config.
    
    Returns:
        Configured LiveAlertDecisionLayer instance
    """
    return LiveAlertDecisionLayer()
