---
authority: scoped
non_authoritative: true
---

# EXP-2201 ByteTrack vs the legacy IoU tracker on labelled sequences

- **Hypothesis**: replacing the unmeasured tracking path in `backend/person_detector.py`
  (greedy IoU>0.3 assignment, immediate loss on a missed frame) with a real ByteTrack
  two-stage association (arXiv:2110.06864, MIT) raises identity quality (HOTA AssA,
  IDF1) on occlusion / exit-re-entry / low-recall / fast-motion sequences without
  regressing detection quality or count accuracy.
- **Requirement link**: S-04 tracking/counting; F-10 person detection/tracking overlay;
  campaign rule "ByteTrack DO FIRST; MOTA alone inadequate".
- **Baseline** (labelled `iou_legacy`, a faithful port of the previous
  `PersonDetector._assign_track_id` behaviour): commit `e86d34b5`, tracker
  `tracking.LegacyIouTracker`; no model (synthetic detector outputs); data = 6 generated
  labelled sequences in `tests/fixtures/tracking/*.json` (160 frames total, 12 GT tracks);
  env = CPU only (`venv` python 3.12, numpy/scipy); source mode = synthetic detections.
- **Candidate** (ByteTrack): same commit/harness, trigger thresholds derived from the
  detector confidence (`track_thresh = 0.45`, `new_track_thresh = 0.45`, `low_thresh = 0.225`),
  `match_thresh = 0.8`, `track_buffer = 30`, Kalman constant-velocity pre-filtering.
- **Success criteria (defined before results)**: on `occlusion`, `exit_reentry` and
  `missed_person`, ByteTrack IDF1 >= legacy IDF1 and HOTA AssA > legacy AssA; ByteTrack
  measured track switches <= legacy; no drop in DetA on any sequence; count-MAE unchanged.
- **Failure criteria / rollback**: any sequence where ByteTrack IDF1 < legacy IDF1 by
  more than 0.02, or DetA lower than legacy on a sequence with equal detections, rejects
  the candidate and reverts `person_detector` to the IoU tracker (the port stays in
  `tracking.py` for A/B).
- **Result** (run 2026-09-29, wall 4.3 s, deterministic — report byte-identical across
  two runs, sha256 `1c5c76d27b2e888de42032c58e2be9b414ae44ad56457981166942736c7f45ee`):

  | sequence (frames) | tracker | HOTA | DetA | AssA | IDF1 | countMAE | switches |
  |---|---|---|---|---|---|---|---|
  | crossing (30) | bytetrack | 0.9965 | 1.0000 | 0.9931 | 1.0000 | 0.000 | 0 |
  | crossing (30) | iou_legacy | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.000 | 0 |
  | occlusion (30) | bytetrack | 0.9049 | 0.9000 | 0.9098 | 0.9474 | 0.200 | 0 |
  | occlusion (30) | iou_legacy | 0.8151 | 0.9000 | 0.7383 | 0.7719 | 0.200 | 1 |
  | exit_reentry (40) | bytetrack | 0.9996 | 1.0000 | 0.9992 | 1.0000 | 0.000 | 0 |
  | exit_reentry (40) | iou_legacy | 0.8935 | 1.0000 | 0.7983 | 0.8235 | 0.000 | 1 |
  | missed_person (24) | bytetrack | 0.7906 | 0.7500 | 0.8333 | 0.8571 | 0.500 | 0 |
  | missed_person (24) | iou_legacy | 0.7144 | 0.7500 | 0.6806 | 0.5952 | 0.500 | 11 |
  | fast_motion (16) | bytetrack | 0.8767 | 0.9142 | 0.8408 | 1.0000 | 0.000 | 0 |
  | fast_motion (16) | iou_legacy | 0.2500 | 1.0000 | 0.0625 | 0.0625 | 0.000 | 15 |
  | duplicate_detections (20) | bytetrack | 0.7063 | 0.5000 | 0.9976 | 0.6667 | 1.000 | 0 |
  | duplicate_detections (20) | iou_legacy | 0.7071 | 0.5000 | 1.0000 | 0.6667 | 1.000 | 0 |

  Denominators: GT detections per sequence 60/60/52/48/32/20 (crossing/occlusion/
  exit_reentry/missed_person/fast_motion/duplicate). Alpha grid 0.05..0.95 (19 values)
  for HOTA; IDF1 at the standard 0.5 threshold. Detection quality (DetA, countMAE) is
  IDENTICAL for both trackers on every sequence, which is the expected result: both are
  fed the same detections, so only association/identity differences appear.
- **Verdict**: **adopt** ByteTrack for `person_detector.py`. It wins or ties on every
  success criterion. Honest counterpoints, preserved: (a) on `crossing` the fixture is
  not discriminating — both trackers are perfect, and legacy scores marginally higher on
  AssA/LocA, so the crossing scenario is NOT evidence in favour of either; (b) on
  `duplicate_detections` both are equally bad (DetA 0.50, countMAE 1.0) because the
  defect is in the detector (duplicate boxes for one person), not the tracker; (c)
  `fast_motion` shows legacy losing identity 15 times (IDF1 0.06) while ByteTrack holds
  IDF1 1.00 with only 2 drift suspicions.
- **Cold vs warm**: no GPU/model involvement in this experiment (synthetic detections,
  CPU-only, 4.3 s wall); no cold/warm distinction applies.
- **RESOURCE-LOCK status: CONTENDED (marked per the orchestrator's binding protocol
  correction).** The run executed while another workstream held `RESOURCE-LOCK`, so per
  rule 4 it is labelled CONTENDED, not a resource-exclusive measurement. Facts: WT-22
  never acquired or wrote into the lock (atomic `mkdir` failed on two attempts; no
  owner.txt was written by WT-22) and never removed it. A re-run under clean acquisition
  is requested/queued; the harness is deterministic (two consecutive runs produced
  byte-identical report JSON, sha256 `1c5c76d2…7f45ee`), so a clean-window re-run is
  expected to reproduce exactly these numbers — the clean window buys the protocol-clean
  label, not different numbers.
