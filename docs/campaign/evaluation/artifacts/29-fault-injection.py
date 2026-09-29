"""WT-29 P3.7 — fault injection probes (in-process, no GPU).

(a) Queue pressure: bounded drop-oldest capture queue (queue_capacity=2, worker
    NOT consuming) with a fast producer of `trigger()` jobs -> `counter["dropped_jobs"]`
    must grow, and `feed()` must never block (no hang). Post-frame overflow must
    bump `counter["dropped_frames"]`.
(b) Storage failure: EVIDENCE_DIR enforced READ-ONLY via Windows ACL deny
    (`icacls ... /deny <user>:(OI)(CI)W`) -> the evidence write must fail with an
    explicit exception naming the failing path; no silent loss.

Run (venv python, from wt-29):
    C:/Users/PCD/Downloads/Final Project AI Sentinel/venv/Scripts/python.exe ^
        docs/campaign/evaluation/artifacts/29-fault-injection.py
"""
from __future__ import annotations

import getpass
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np  # noqa: E402


def probe_queue_pressure() -> dict:
    from capture_queue import IncidentCapture  # noqa: PLC0415

    # Worker disabled -> jobs stay pending -> queue overflow is observable.
    cap = IncidentCapture(queue_capacity=2, max_post_frames_per_job=2, start_worker=False)
    frame = np.zeros((16, 16, 3), dtype=np.uint8)

    t0 = time.monotonic()
    for i in range(20):
        cap.trigger(alert_id=f"a{i}", alert_time=time.monotonic())
    trigger_elapsed = time.monotonic() - t0

    # Frame pressure inside a live job window (feed must stay non-blocking).
    job = cap.trigger(alert_id="pressure", alert_time=time.monotonic())
    t0 = time.monotonic()
    hung = threading.Event()

    def feeder():
        for i in range(500):
            cap.feed(captured_at=time.monotonic(), frame=frame, frame_sequence=i)
        hung.set()

    th = threading.Thread(target=feeder, daemon=True)
    th.start()
    finished = hung.wait(timeout=15)
    feed_elapsed = time.monotonic() - t0
    return {
        "queue_capacity": cap.queue_capacity,
        "triggers": 21,
        "trigger_elapsed_s": round(trigger_elapsed, 4),
        "feed_500_finished_within_15s": finished,
        "feed_elapsed_s": round(feed_elapsed, 4),
        "counter": dict(cap.counter),
        "no_hang": finished and trigger_elapsed < 5,
    }


def probe_storage_failure() -> dict:
    user = getpass.getuser()
    tmp = Path(tempfile.mkdtemp(prefix="wt29-evidence-"))
    ro = tmp / "readonly-evidence"
    ro.mkdir()
    subprocess.run(["icacls", str(ro), "/deny", f"{user}:(OI)(CI)W"],
                   capture_output=True, text=True, check=False)
    out = {"evidence_dir": str(ro), "enforced_by": f"icacls deny {user}:(OI)(CI)W"}
    target = ro / "alert-test.mp4"
    try:
        with target.open("wb") as fh:
            fh.write(b"\x00" * 1024)
        out["write_succeeded"] = True
        out["explicit_error"] = False
    except Exception as exc:  # noqa: BLE001 — loud failure IS the expected result
        out["write_succeeded"] = False
        out["explicit_error"] = True
        out["error_type"] = type(exc).__name__
        out["error_message"] = str(exc)[:300]
        out["error_mentions_path"] = "alert-test.mp4" in str(exc) or str(ro) in str(exc)
    finally:
        subprocess.run(["icacls", str(ro), "/remove:d", user],
                       capture_output=True, text=True, check=False)
        try:
            target.unlink()
        except OSError:
            pass
        try:
            ro.rmdir()
            tmp.rmdir()
        except OSError:
            pass
    return out


def main() -> int:
    results = {
        "queue_pressure": probe_queue_pressure(),
        "storage_failure": probe_storage_failure(),
        "clock_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out_path = Path(__file__).parent / "29-fault-injection.json"
    out_path.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
