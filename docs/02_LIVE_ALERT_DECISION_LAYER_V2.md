# Live Alert Decision Layer V2

## Problem

The live pipeline could show false-positive behavior when:

- a single transient spike crossed the model threshold
- repeated stale-frame updates acted like multiple confirmation votes
- the UI relied on raw model prediction instead of a conservative temporal decision

This was unsafe for a live graduation demo because a single bad burst could look like a real visible violence alert.

## Solution

V2 adds a temporal decision layer on top of model output. It does not retrain the model, change weights, or modify the base model threshold. It only decides when a visible alert is allowed to appear.

## State Machine

- `NORMAL`
  - calibrated probability is below watch threshold
- `WATCH`
  - probability is high enough to monitor but confirmation rule is not met yet
- `CONFIRMED_VIOLENCE`
  - the temporal confirmation rule is satisfied
- `COOLDOWN`
  - suppresses repeated visible alerts immediately after confirmation

## Thresholds

- `WATCH_THRESHOLD = 0.45`
- `CONFIRM_THRESHOLD = 0.65`
- `CONFIRM_N = 2`
- `CONFIRM_M = 3`
- `MIN_DECISION_INTERVAL_SECONDS = 0.50`
- `ALERT_COOLDOWN_SECONDS = 3.0`

## Temporal Confirmation Rule

The visible violence alert is allowed only when at least `2` of the last `3` accepted decision windows are at or above `0.65`.

The accepted-decision requirement matters because V2 rejects too-soon duplicate samples. That is the specific protection against stale repeated frame probabilities behaving like multiple votes.

## Why `confirmed_alert` Controls The Red Alert

- `confirmed_alert` represents the final conservative temporal decision
- `model_prediction` is only the raw internal inference signal
- raw inference can be noisy, stale, or temporarily spiky
- the dashboard must bind the visible red alert to `confirmed_alert` / `confirmedAlert` only

If the UI uses `model_prediction` directly, V2 protection is bypassed.

## Why `model_prediction` Remains Internal

It is still useful for:

- debugging
- telemetry
- tuning review
- explaining why the state machine entered `WATCH`

It must not drive the public visible alert state by itself.

## API Integration Notes

The backend exposes the decision-layer status through:

- `GET /system/status`
- `POST /decision_layer/reset`

The API payload includes both snake_case and camelCase fields so the frontend can safely consume:

- `confirmed_alert` and `confirmedAlert`
- `alert_state` and `alertState`
- `decision_sample_accepted` and `decisionSampleAccepted`

## Test Results

- `FINAL_LIVE_ALERT_API_CHECK: PASS`
- `SAFE_TO_RUN_LIVE_DEMO: True`
- `VIOLENCE_CLS = 1` preserved
- base runtime threshold remains `0.45`
- false-positive replay result:
  - replay count: `5`
  - still confirmed after V2: `0`
  - conclusion: old false positives no longer produce confirmed live alerts

## Non-Goals

V2 does not:

- train the model
- change weights
- replace the classifier
- alter the base model compatibility path
