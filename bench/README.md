# Measurement evidence

These are dated diagnostic artifacts, not current project instructions. Read ../docs/CURRENT.md and ../docs/ISSUES.md. No runtime gate is certified by this README.

From the repository root using the existing environment:

```powershell
& ./venv/Scripts/python.exe -B -m pytest bench/test_common.py bench/test_summary.py -q -p no:cacheprovider
& ./venv/Scripts/python.exe -m bench.run --source demo_assets/videos/Wq0BuA8GM84_0.avi --all-detection --seconds 75 --warmup 25 --output bench/results/new-measurement
```

Choose a new output directory and avoid concurrent benchmarks. The runner isolates storage and disables external notifications/reporting. It accepts an existing file or USB index; RTSP profile support remains pending. Capture timestamps now exist, but independent event onset/labels and glass latency remain unmeasured. `--extended-controls` measures unchanged `/set_threshold`, `/set_cooldown` and `/decision/config` requests. This does not exercise every mutating endpoint or prove live G-15. Source hashes accompany saved reports; invalid/failed runs remain evidence of failure, never baselines for success. Runtime logs, traces and media remain ignored. `--chunk-traces` flushes lossless segments to bound instrumentation memory during long runs. No 60-minute live soak is certified.

Temperature-calibration candidate tooling is available through `python -m bench.calibrate --help`; input labels remain an external evidence requirement. Use the same source SHA, workload and environment when comparing throughput. A different resolution/video is a separate diagnostic, not a valid baseline comparison.

WT-12 evaluation tooling (`bench/eval/`, protocol `docs/campaign/eval/12-eval-protocol.md`): `bench.fetch_fixtures` acquires rights-checked fixtures into an external media directory (media never enter git; the publisher's rights statement is re-verified at acquisition); `bench.eval.contracts` validates the fixture manifest (label provenance publisher/independent-human only; duplicate-media and session-straddle rejection); `bench.eval.score_fixtures` records model outputs per fixture (windows/detections/alerts/tracks, `file-media` source mode); `bench.eval.evaluate` computes frame/window/event metrics, counting metrics, difficulty slices and cluster-bootstrap CIs from recorded outputs + manifest. Self-tests: `python -m pytest bench/eval/test_eval.py`. No live-camera gate or 60-minute live soak has been delivered; time-to-detection remains unmeasured while no fixture carries an independently labeled onset.
