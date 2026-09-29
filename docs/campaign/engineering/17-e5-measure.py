"""WT-17 E-5 transport latency harness (MJPEG publish-to-display).

Two subcommands, deliberately browser-agnostic so the same artifacts can be
re-analysed offline:

  fixture  --out <fixture.mp4> [--seconds 90]
      Generate the timestamped fixture with the bundled ffmpeg: testsrc2 with a
      burned-in millisecond timer (media-time). Records size + sha256.

  analyze  --fixture <fixture.mp4> --samples <samples.json> --out <report.json>
      samples.json: [{"wall_ms": <epoch ms at capture>, "screenshot": "<png>",
                      "video_box": [x, y, w, h]}]  (video_box = the <img> element
                      rectangle in the screenshot's pixel space)
      Identifies the displayed fixture frame by template-matching the burned-in
      timer region, then reports (wall_ms - T0) - media_ms per sample, where T0
      is the wall time when media time 0 was displayed (calibrated from the
      earliest identified sample; uncertainty disclosed in the report).

Runbook (RESOURCE-LOCK discipline is binding; see docs/campaign/experiments/17-e5-transport-latency.md):
  1. atomic `mkdir .../RESOURCE-LOCK`; write owner.txt; verify it is yours.
  2. python 17-e5-measure.py fixture --out <run>/e5-timer-90s.mp4
  3. backend: cd backend && <venv>/python.exe -m uvicorn api:app --port 8002
     with an untracked backend/camera_profiles.yml pointing CAM-01 at the fixture.
  4. frontend: npm run dev  (open http://localhost:3000, Live Monitor on CAM-01)
  5. capture >= 30 samples (wall_ms + screenshot + video_box) — one per ~1 s.
  6. python 17-e5-measure.py analyze --fixture ... --samples ... --out ...
  7. release the lock (remove the dir) and message the queue.
Explicitly NOT glass-to-alert: the fixture has no camera; only publish-to-display.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import cv2
import numpy as np

# Burned-in timer geometry (must match the ffmpeg drawtext filter below).
TIMER_X, TIMER_Y, TIMER_W, TIMER_H = 20, 20, 300, 100
FIXTURE_SIZE = (854, 480)
FIXTURE_FPS = 30
# Media ms is rendered as digits; identification uses an exact-frame search, so the
# only assumption is that the timer region is unique per frame (true at 30 fps).


def _bundled_ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def make_fixture(out_path: Path, seconds: int = 90) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    font = "C\\:/Windows/Fonts/arialbd.ttf"
    drawtext = (
        f"drawtext=fontfile='{font}':text='%{{eif\\:t*1000\\:d}}':"
        f"fontcolor=white:fontsize=72:box=1:boxcolor=black@0.75:x={TIMER_X}:y={TIMER_Y}"
    )
    cmd = [
        _bundled_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size={FIXTURE_SIZE[0]}x{FIXTURE_SIZE[1]}:rate={FIXTURE_FPS}:duration={seconds}",
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    facts = {
        "path": str(out_path), "sha256": digest, "seconds": seconds,
        "size": list(FIXTURE_SIZE), "fps": FIXTURE_FPS,
        "provenance": "generated locally with the bundled imageio-ffmpeg binary (testsrc2 + drawtext); not a dataset/asset copy",
    }
    print(json.dumps(facts, indent=2))
    return facts


def _timer_roi(frame: np.ndarray) -> np.ndarray:
    roi = frame[TIMER_Y:TIMER_Y + TIMER_H, TIMER_X:TIMER_X + TIMER_W]
    return cv2.cvtColor(cv2.resize(roi, (TIMER_W, TIMER_H)), cv2.COLOR_BGR2GRAY)


def _index_fixture(fixture: Path) -> np.ndarray:
    cap = cv2.VideoCapture(str(fixture))
    rois = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        rois.append(_timer_roi(frame))
    cap.release()
    if not rois:
        raise SystemExit(f"could not decode fixture frames from {fixture}")
    return np.stack(rois)


def _contained_rect(box: list[int]) -> tuple[int, int, int, int]:
    x, y, w, h = box
    video_aspect = FIXTURE_SIZE[0] / FIXTURE_SIZE[1]
    if w / max(1, h) > video_aspect:
        height = h
        width = int(round(h * video_aspect))
    else:
        width = w
        height = int(round(w / video_aspect))
    return x + (w - width) // 2, y + (h - height) // 2, width, height


def analyze(fixture: Path, samples: list[dict], anchor: dict | None = None) -> dict:
    rois = _index_fixture(fixture)
    rows = []
    for sample in samples:
        shot = cv2.imread(str(sample["screenshot"]))
        if shot is None:
            rows.append({"wall_ms": sample.get("wall_ms"), "match": None, "reason": "screenshot unreadable"})
            continue
        wall_before = sample.get("wall_before_ms", sample.get("wall_ms"))
        wall_after = sample.get("wall_after_ms", sample.get("wall_ms"))
        wall_ms = (wall_before + wall_after) / 2.0 if wall_before is not None and wall_after is not None else sample.get("wall_ms")
        vx, vy, vw, vh = _contained_rect(sample["video_box"])
        scale_x = FIXTURE_SIZE[0] / max(1, vw)
        scale_y = FIXTURE_SIZE[1] / max(1, vh)
        rx = int(TIMER_X * scale_x) + vx
        ry = int(TIMER_Y * scale_y) + vy
        rw = max(2, int(TIMER_W * scale_x))
        rh = max(2, int(TIMER_H * scale_y))
        crop = shot[ry:ry + rh, rx:rx + rw]
        if crop.size == 0:
            rows.append({"wall_ms": sample["wall_ms"], "match": None, "reason": "timer region outside screenshot"})
            continue
        probe = cv2.cvtColor(cv2.resize(crop, (TIMER_W, TIMER_H)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        diffs = np.abs(rois.astype(np.float32) - probe[None, :, :]).mean(axis=(1, 2))
        index = int(np.argmin(diffs))
        rows.append({
            "wall_before_ms": wall_before,
            "wall_after_ms": wall_after,
            "wall_ms": round(wall_ms, 1) if wall_ms is not None else None,
            "frame_index": index,
            "media_ms": round(index * 1000.0 / FIXTURE_FPS, 1),
            "match_distance": round(float(diffs[index]), 2),
            "second_best_distance": round(float(np.partition(diffs, 1)[1]), 2),
        })
    matched = [r for r in rows if r.get("media_ms") is not None]
    if not matched:
        return {"samples": len(samples), "matched": 0, "latency_ms": None, "rows": rows}
    t0 = min(r["wall_ms"] - r["media_ms"] for r in matched)  # earliest (media0 → wall) calibration
    latencies = sorted(r["wall_ms"] - t0 - r["media_ms"] for r in matched)
    def pct(p: float) -> float:
        return round(float(np.percentile(latencies, p)), 1)
    report = {
        "samples": len(samples),
        "matched": len(matched),
        "denominator": f"{len(matched)}/{len(samples)} samples identified",
        "t0_wall_ms": t0,
        "t0_note": "wall time when media time 0 was displayed (calibrated from the earliest identified sample; uncertainty = one sample interval + matching error)",
        "latency_ms": {"p05": pct(5), "median": pct(50), "p95": pct(95), "min": latencies[0], "max": latencies[-1]},
        "scope": "MJPEG-over-HTTP publish-to-display on the local browser; NOT glass-to-alert",
        "rows": rows,
    }
    anchor_wall = (anchor or {}).get("boundary_arrival_wall_ms")
    arrival_p95 = ((anchor or {}).get("publish_to_arrival_ms") or {}).get("p95")
    if anchor_wall is not None:
        xs = sorted(r["wall_ms"] - anchor_wall - r["media_ms"] for r in matched)
        def xpct(p: float) -> float:
            return round(float(np.percentile(xs, p)), 1)
        upper = xpct(95) + arrival_p95 if isinstance(arrival_p95, (int, float)) else None
        report["publish_to_paint_bounded_ms"] = {
            "x_p05": xpct(5), "x_median": xpct(50), "x_p95": xpct(95),
            "anchor_wall_ms": anchor_wall,
            "arrival_p95_ms": arrival_p95,
            "upper_bound_p95_ms": upper,
            "bound_note": ("absolute publish->paint = x + publish->arrival; arrival is measured "
                           f"separately on the same machine, so absolute p95 <= x_p95 + {arrival_p95} ms"),
        }
    return report


def stream_latency(fixture: Path, url: str, seconds: float, camera_id: str) -> dict:
    """Measure publish→arrival latency absolutely, anchored on the media loop boundary.

    Rationale: the burned-in timer gives the media clock; the fixture is wall-paced,
    and the media clock restarts at every loop boundary. Observing v drop between two
    consecutive parts brackets that boundary to one part interval (~33 ms at 30 fps),
    which turns W - (T0_boundary + v) into an ABSOLUTE publish→arrival figure that no
    cross-clock subtraction is involved in (both stamps are local wall time).
    """
    import httpx

    cap = cv2.VideoCapture(str(fixture))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(_timer_roi(frame))
    cap.release()
    index = np.stack(frames).astype(np.float32)

    boundary_at = None
    rows = []
    prev_v = None
    deadline = time.time() + seconds
    with httpx.stream("GET", url, params={"camera_id": camera_id}, timeout=10.0) as response:
        response.raise_for_status()
        buffer = b""
        for chunk in response.iter_bytes():
            buffer += chunk
            while b"\r\n\r\n" in buffer:
                head, rest = buffer.split(b"\r\n\r\n", 1)
                if b"Content-Type: image/jpeg" not in head:
                    buffer = rest
                    continue
                length_marker = b"Content-Length: "
                if length_marker in head:
                    length = int(head.split(length_marker, 1)[1].split(b"\r\n", 1)[0])
                    if len(rest) < length:
                        break
                    body, buffer = rest[:length], rest[length:]
                else:
                    end = rest.find(b"\r\n--frame")
                    if end < 0:
                        break
                    body, buffer = rest[:end], rest[end:]
                arrived = time.time() * 1000.0
                seq_header = _header_int(head, b"X-Frame-Sequence")
                age_header = _header_float(head, b"X-Frame-Age-Ms")
                probe = _part_timer_roi(body)
                if probe is None:
                    continue
                if prev_v is None:
                    diffs = np.abs(index - probe[None, :, :]).mean(axis=(1, 2))
                    v = int(np.argmin(diffs)) * 1000.0 / FIXTURE_FPS
                else:
                    lo = max(0, int((prev_v - 250) * FIXTURE_FPS / 1000.0))
                    hi = min(len(index), int((prev_v + 250) * FIXTURE_FPS / 1000.0) + 1)
                    diffs = np.abs(index[lo:hi] - probe[None, :, :]).mean(axis=(1, 2))
                    v = (lo + int(np.argmin(diffs))) * 1000.0 / FIXTURE_FPS
                if prev_v is not None and v + 200 < prev_v:
                    boundary_at = arrived  # media clock restarted in this part
                prev_v = v
                if boundary_at is not None:
                    rows.append({
                        "arrived_wall_ms": round(arrived, 1),
                        "frame_sequence": seq_header,
                        "media_ms": round(v, 1),
                        "server_age_at_publish_ms": age_header,
                        "publish_to_arrival_ms": round(arrived - (boundary_at + v), 1),
                    })
            if time.time() > deadline:
                break
    latencies = sorted(r["publish_to_arrival_ms"] for r in rows)
    ages = sorted(r["server_age_at_publish_ms"] for r in rows if r["server_age_at_publish_ms"] is not None)
    def pct(values: list[float], p: float) -> float | None:
        return round(float(np.percentile(values, p)), 1) if values else None
    return {
        "url": url,
        "camera_id": camera_id,
        "samples": len(rows),
        "boundary_arrival_wall_ms": round(boundary_at, 1) if boundary_at is not None else None,
        "boundary_anchor_note": "T0 = first part carrying restarted media time; anchor error <= one part interval (~33 ms at 30 fps)",
        "publish_to_arrival_ms": {"p05": pct(latencies, 5), "median": pct(latencies, 50), "p95": pct(latencies, 95)},
        "server_capture_to_publish_ms": {"p05": pct(ages, 5), "median": pct(ages, 50), "p95": pct(ages, 95)},
        "scope": "MJPEG-over-HTTP publish→arrival on this machine (localhost); NOT glass-to-alert, NOT browser paint",
        "rows": rows,
    }


def _header_int(head: bytes, name: bytes) -> int | None:
    marker = name + b": "
    if marker not in head:
        return None
    try:
        return int(head.split(marker, 1)[1].split(b"\r\n", 1)[0])
    except ValueError:
        return None


def _header_float(head: bytes, name: bytes) -> float | None:
    marker = name + b": "
    if marker not in head:
        return None
    try:
        return float(head.split(marker, 1)[1].split(b"\r\n", 1)[0])
    except ValueError:
        return None


def _part_timer_roi(body: bytes) -> np.ndarray | None:
    prefix = b"\xff\xd8"
    start = body.find(prefix)
    if start < 0:
        return None
    image = cv2.imdecode(np.frombuffer(body[start:], np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    if image.shape[1] != FIXTURE_SIZE[0]:
        scale = image.shape[1] / FIXTURE_SIZE[0]
        x = int(TIMER_X * scale)
        y = int(TIMER_Y * scale)
        w = max(2, int(TIMER_W * scale))
        h = max(2, int(TIMER_H * scale))
        roi = image[y:y + h, x:x + w]
    else:
        roi = image[TIMER_Y:TIMER_Y + TIMER_H, TIMER_X:TIMER_X + TIMER_W]
    if roi.size == 0:
        return None
    gray = cv2.cvtColor(cv2.resize(roi, (TIMER_W, TIMER_H)), cv2.COLOR_BGR2GRAY)
    return gray.astype(np.float32)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fx = sub.add_parser("fixture")
    fx.add_argument("--out", required=True, type=Path)
    fx.add_argument("--seconds", type=int, default=90)
    an = sub.add_parser("analyze")
    an.add_argument("--fixture", required=True, type=Path)
    an.add_argument("--samples", required=True, type=Path)
    an.add_argument("--anchor", type=Path, default=None,
                    help="optional stream-report JSON: bounds absolute publish->paint using the measured arrival leg")
    an.add_argument("--out", required=True, type=Path)
    st = sub.add_parser("stream")
    st.add_argument("--fixture", required=True, type=Path)
    st.add_argument("--url", default="http://localhost:8002/video_feed")
    st.add_argument("--camera-id", default="CAM-01")
    st.add_argument("--seconds", type=float, default=45.0)
    st.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.command == "fixture":
        make_fixture(args.out, args.seconds)
        return 0
    if args.command == "stream":
        report = stream_latency(args.fixture, args.url, args.seconds, args.camera_id)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
        print(f"rows: {len(report['rows'])} → {args.out}")
        return 0
    anchor = json.loads(args.anchor.read_text(encoding="utf-8")) if args.anchor else None
    report = analyze(args.fixture, json.loads(args.samples.read_text(encoding="utf-8")), anchor)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    print(f"rows: {len(report['rows'])} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
