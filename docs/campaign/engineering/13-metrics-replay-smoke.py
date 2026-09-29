"""WT-13 / S-08 module-level replay smoke: synthesise a 75 s pipeline timeline and export it.

Reproduce from the worktree root with the project venv interpreter (the one the API and
workers run under, so the export reports the deployed clock quantization):

    ./venv/Scripts/python.exe docs/campaign/engineering/13-metrics-replay-smoke.py /tmp/sample.json

The API is importable only after the SC-10 cherry-pick (`b7d1f43`) and there is no camera
device, so this drives the telemetry ingest exactly as the runtime result dict would and
dumps the `sentinel-metrics-export/1` payload. Nothing here is a GPU benchmark: the numbers
come from a deterministic synthetic timeline (cadences stated below) and the counter windows
are compressed (CPU-speed ingest), which the export's `runProvenance.timeline` records.
`13-metrics-export-sample.json` in this directory is one such artifact produced by this script
(timestamps differ per run).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BACKEND_DIR = next(parent / "backend" for parent in Path(__file__).resolve().parents
                    if (parent / "backend" / "metrics.py").is_file())
sys.path.insert(0, str(BACKEND_DIR))

import metrics  # noqa: E402  (import after sys.path bootstrap)

SRC_FPS = 25.0          # synthetic capture cadence
RENDER_FPS = 24.0       # synthetic render/publication cadence
VIOLENCE_EVERY = 4      # completed violence inferences per second
WEAPON_EVERY = 2        # completed weapon inferences per second
PERSON_EVERY = 1        # completed person inferences per second
DURATION_SECONDS = 75


def main() -> int:
    telemetry = metrics.PipelineMetrics()
    telemetry.set_run_provenance(
        sourceMode="file-media",
        adapterState="B-3-stubbed (go2rtc_bridge/openrouter_reporting absent at baseline)",
        timeline="synthetic 75 s @25 fps timeline, ingested at CPU speed (counter windows are compressed, not wall-clock 75 s)",
        note="no GPU benchmark, no camera device, no models loaded",
    )
    frames_read = 0
    person = violence = weapon = 0
    dropped = 0
    publications = 0

    steps = int(DURATION_SECONDS * SRC_FPS)
    for index in range(steps):
        frames_read += 1
        if index % int(SRC_FPS / RENDER_FPS) == 0:
            publications += 1
        if index % int(SRC_FPS / VIOLENCE_EVERY) == 0:
            violence += 1
        if index % int(SRC_FPS / WEAPON_EVERY) == 0:
            weapon += 1
        if index % int(SRC_FPS / PERSON_EVERY) == 0:
            person += 1
        if index > steps - int(SRC_FPS * 5) and index % 7 == 0:
            dropped += 1  # a 5 s burst at the tail, to exercise the drop counter
        snap = {
            "processRunId": "smoke-run-1",
            "workerPid": 4242,
            "inferenceGeneration": 1,
            "inference_sequence": publications,
            "capture_timestamp": time.monotonic() - 0.04,
            "captureClockBase": "monotonic-gettickcount64",
            "frameAgeMs": 38.0 + (index % 17),
            "frameAgeAtPublicationMs": 45.0 + (index % 23),
            "frameAgeClockSource": "monotonic-capture",
            "stageFrameReadMs": 5.1 + (index % 5) * 0.3,
            "stageCaptureToQueueMs": 2.4,
            "stagePreprocessMs": 3.2 + (index % 7) * 0.2,
            "stageEnqueueToDequeueMs": 9.0 + (index % 11) * 0.5,
            "stageInferenceWaitMs": 7.5 + (index % 9) * 0.4,
            "stageInferenceComputeMs": 21.0 + (index % 13) * 0.6,
            "inferenceComputeSynced": True,
            "captureFps": SRC_FPS,
            "renderFps": RENDER_FPS,
            "frameQueueDepth": 1 + (index % 3),
            "frameQueueDropped": dropped,
            "frameQueueDroppedDerived": dropped,
            "resultQueueDepth": index % 4,
            "resultQueueDropped": 0,
            "backlogFrames": index % 2,
            "personCompletedCount": person,
            "violenceCompletedCount": violence,
            "weaponCompletedCount": weapon,
            "framesReadCount": frames_read,
            "alert_state": "NORMAL",
            "updatedAt": time.time(),
        }
        telemetry.observe_detection_snapshot(snap, camera_id="CAM-01")

    export = telemetry.export_snapshot()
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("13-metrics-export-sample.json")
    payload = json.dumps(export, indent=2, allow_nan=False, sort_keys=False)
    out_path.write_text(payload + "\n", encoding="utf-8", newline="\n")

    print(f"observations={export['observation']['ingestCount']} "
          f"publications={export['observation']['distinctSequenceCount']}")
    print("captureFps", export["rates"]["captureFps"])
    print("renderFps", export["rates"]["renderFps"])
    print("publicationFps", export["rates"]["publicationFps"])
    print("completedInferenceFps", export["rates"]["completedInferenceFps"])
    print("frameAge.atInferenceStart", export["frameAgeMs"]["atInferenceStart"])
    print("frameAge.atPublication", export["frameAgeMs"]["atPublication"])
    print("stage.inferenceCompute", export["stageLatencyMs"]["inferenceCompute"])
    print("queues.frame", {key: value for key, value in export["queues"]["frame"].items() if key != "depthDist"})
    print("faults", export["faults"])
    print("subsystems", {key: entry["status"] for key, entry in export["subsystems"].items()})
    print("clockQuantization", {key: value for key, value in export["clockQuantization"].items()
                                if key.endswith("ResolutionMs")})
    print("resources", export["resources"])
    print(f"wrote {out_path} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
