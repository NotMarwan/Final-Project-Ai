# Stage 12 External Eval

> See also: [Project Status](00_PROJECT_STATUS.md) | [Live Alert Decision Layer V2](02_LIVE_ALERT_DECISION_LAYER_V2.md) | [README](../README.md)

## Dataset

- Dataset: `UBI-FightsAll`
- Total videos found: `1000`
- Normal found: `784`
- Violence found: `216`
- Copied subset: `20 normal / 20 violence`
- Processed: `40`
- Errors: `0`

## Runtime Assumptions

- Threshold: `0.45`
- `VIOLENCE_CLS = 1`
- Stable runtime reference model SHA256:
  `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`

## Metrics

- Accuracy: `0.8`
- Precision: `0.7727`
- Recall: `0.85`
- F1: `0.8095`
- Balanced accuracy: `0.8`
- TN: `15`
- FP: `5`
- FN: `3`
- TP: `17`

## Final Recommendation

- Recommendation: `STAGE12_EXTERNAL_GENERALIZATION_REVIEW`
- Reason: recall below `0.90`

## Interpretation

The model generalized reasonably on an external dataset, but recall did not meet the stricter deployment target. That means the Stage 12 result supported continued review rather than an unconditional generalization pass.

## Important Follow-up Result

Later, the live alert decision layer V2 reduced confirmed false alerts on the `5` old false-positive clips to:

- `STILL_CONFIRMED_ALERT_COUNT: 0`

That does not rewrite the Stage 12 model-level metrics; it improves the live runtime safety layer on top of those model outputs.
