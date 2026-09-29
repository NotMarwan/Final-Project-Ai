"""WT-17 E-5 browser sample collector (Playwright, py -3.14).

Collects >= N samples of (wall clock before, screenshot, wall clock after, video box)
from a real Chromium against the MJPEG stream, for 17-e5-measure.py `analyze`.

  py -3.14 17-e5-samples.py --mode app --samples 40 --out <run>/samples.json --shots <run>/shots
  py -3.14 17-e5-samples.py --mode direct --samples 40 ...

--mode app    drives the real operator UI (Live Monitor section of the dashboard)
--mode direct renders a minimal <img> page for the same /video_feed URL

The screenshot itself takes time; both wall clocks are recorded so the analyzer can
report the paint instant as a window instead of pretending to sub-millisecond
precision. Headless throttling flags are set so background tabs do not slow paint.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright

LIVE_NAV_LABEL = "المراقبة الحية"
CAMERA_ALT_PREFIX = "بث الكاميرا"


def collect(mode: str, samples: int, app_url: str, feed_url: str, camera_id: str,
            out_dir: Path, interval_s: float) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    shots = out_dir / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
        ])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        if mode == "app":
            page.goto(app_url, wait_until="domcontentloaded", timeout=60_000)
            page.get_by_text(LIVE_NAV_LABEL, exact=False).first.click(timeout=30_000)
            page.wait_for_selector(f'img[alt^="{CAMERA_ALT_PREFIX}"]', timeout=60_000)
            handle = page.query_selector(f'img[alt^="{CAMERA_ALT_PREFIX}"]')
        else:
            page.set_content(
                "<body style='margin:0;background:#000'>"
                f"<img id='v' src='{feed_url}?camera_id={camera_id}' style='width:854px;height:480px'>"
                "</body>"
            )
            page.wait_for_selector("#v", timeout=30_000)
            handle = page.query_selector("#v")

        # Wait for a first painted frame before sampling.
        page.wait_for_timeout(3_000)
        for index in range(samples):
            box = handle.bounding_box()
            if box is None:
                rows.append({"index": index, "error": "element has no box"})
                continue
            before = page.evaluate("Date.now()")
            shot = shots / f"sample-{index:03d}.png"
            handle.screenshot(path=str(shot))
            after = page.evaluate("Date.now()")
            rows.append({
                "index": index,
                "wall_before_ms": before,
                "wall_after_ms": after,
                "screenshot": str(shot).replace("\\", "/"),
                "video_box": [0, 0, int(round(box["width"])), int(round(box["height"]))],
            })
            time.sleep(interval_s)
        browser.close()
    report = {
        "mode": mode,
        "app_url": app_url,
        "feed_url": feed_url,
        "camera_id": camera_id,
        "samples": len(rows),
        "note": "wall_after - wall_before is the screenshot duration; the displayed frame was painted inside that window",
        "rows": rows,
    }
    (out_dir / "samples.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["app", "direct"], default="app")
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--app-url", default="http://localhost:3000")
    parser.add_argument("--feed-url", default="http://localhost:8002/video_feed")
    parser.add_argument("--camera-id", default="CAM-01")
    parser.add_argument("--interval", type=float, default=0.8)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = collect(args.mode, args.samples, args.app_url, args.feed_url, args.camera_id, args.out, args.interval)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    print(f"rows: {len(report['rows'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
