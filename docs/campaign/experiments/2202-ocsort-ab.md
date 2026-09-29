---
authority: scoped
non_authoritative: true
---

# EXP-2202 OC-SORT A/B against ByteTrack (same fixtures, same detections)

- **Hypothesis**: OC-SORT (arXiv:2203.14360, MIT) — the campaign's "A/B if cheap" option —
  does not beat the ByteTrack implementation on these sequences, so ByteTrack stays the
  default and OC-SORT remains a config-selectable alternative (`PERSON_TRACKER=ocsort`).
- **Requirement link**: S-04; campaign rule "ByteTrack DO FIRST; OC-SORT A/B".
- **Baseline**: ByteTrack defaults as shipped (`tracking.ByteTrack`), commit on
  `codex/sentinel-22-tracking-counting`, synthetic labelled sequences
  (`tests/fixtures/tracking/*.json`), CPU only, no model.
- **Candidate**: `tracking.OCSortTracker` — same Kalman/association thresholds, plus
  observation-centric direction cost (`angle_weight = 0.4`) and observation-centric
  recovery after a gap (virtual interpolated observations). No ReID branch, no
  appearance features, per policy.
- **Success criteria (before results)**: OC-SORT HOTA/IDF1 within 0.02 of ByteTrack on
  every sequence; either tracker may ship as default.
- **Failure criteria / rollback**: if OC-SORT fails a sequence badly (IDF1 gap > 0.02) it
  remains selectable but is documented as non-default; no rollback needed since ByteTrack
  is the default.
- **Result** (same run as EXP-2201, report sha256 `1c5c76d2…7f45ee`): OC-SORT is
  identical to ByteTrack on `crossing` (0.9965/1.0000), `exit_reentry` (0.9996/1.0000),
  `duplicate_detections` (0.7063/0.6667), `missed_person` (0.7906/0.8571) and
  `fast_motion` (0.8767/1.0000); it is slightly worse on `occlusion`
  (HOTA 0.8940 vs 0.9049, IDF1 tie at 0.9474). Failure flags are identical in every case.
  Denominator: 160 frames / 6 sequences / 3 trackers, deterministic (byte-identical
  report across two runs).
- **Verdict**: **adapt** — keep ByteTrack as the default (`PERSON_TRACKER` env + tracker
  parameter), keep OC-SORT as an exercised, tested alternative. The sequences are
  synthetic and mostly single-object, so this A/B does NOT establish which tracker is
  better on real footage; that requires WT-12 fixtures.
- **Cold vs warm**: not applicable (CPU-only synthetic harness, no GPU/model).
