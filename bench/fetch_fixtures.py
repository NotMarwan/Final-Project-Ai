"""Rights-checked, reproducible acquisition of WT-12 evaluation fixtures.

Design rules (docs/campaign/eval/12-eval-protocol.md):
- ORIGINAL PUBLISHERS ONLY. Unofficial mirrors are never used (RWF-2000 rule).
- The publisher's rights statement is fetched and checked AT ACQUISITION TIME;
  acquisition aborts if the verified quote no longer appears on the source page.
- Large media stay OUT of git: clips are written to a declared external
  directory (default C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12-fixtures,
  override with --media-root or SENTINEL_FIXTURE_ROOT). The manifest records
  SHA-256 + media facts so any copy can be verified byte-for-byte.
- Labels come from the publisher's action annotation ONLY. Nothing here ever
  infers labels from a model.

Usage (from the repository root):
    python -m bench.fetch_fixtures --acquire --write-manifest docs/campaign/eval/12-fixture-manifest.json
    python -m bench.fetch_fixtures --verify --manifest docs/campaign/eval/12-fixture-manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from bench.common import ROOT, sha256, write_json

DATASET_PAGE = "https://www.csc.kth.se/cvap/actions/"
BASE = DATASET_PAGE
VERIFIED_QUOTE = ("The database is publicly available for non-commercial use. "
                  "Please refer to [Schuldt, Laptev and Caputo, Proc. ICPR'04, Cambridge, UK] "
                  "if you use this database in your publications.")
# Substantive fragments checked against the tag-stripped publisher page. The
# human-readable quote above is what goes into the manifest; the gate works on
# fragments so markup/link churn cannot silently pass AND cannot falsely refuse.
RIGHTS_FRAGMENTS = ("publicly available for non-commercial use",
                    "schuldt, laptev and caputo",
                    "if you use this database in your publications")
VERIFIED_ON = "2026-09-29"
DEFAULT_MEDIA_ROOT = Path("C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12-fixtures")
ARCHIVE_LIMIT = 400 * 1024 * 1024
CLIP_LIMIT = 40 * 1024 * 1024
SUBJECTS = tuple(f"person{i:02d}" for i in range(1, 13))
SCENARIO = "d1"

# Publisher action -> evaluation category/subcategory. The boxing action is
# STAGED single-person punching: a violence-like positive for clip/window-level
# recall only, with NO onset annotation (time-to-detection stays unmeasurable).
ACTIONS = {
    "walking": {"category": "negative", "subcategory": "walking"},
    "handwaving": {"category": "negative", "subcategory": "waving"},
    "handclapping": {"category": "negative", "subcategory": "clapping_fast_arms"},
    "jogging": {"category": "negative", "subcategory": "sports_motion"},
    "running": {"category": "negative", "subcategory": "sports_motion"},
    "boxing": {"category": "positive", "subcategory": "violence_staged"},
}
# Priority order for bandwidth-limited acquisition; later actions are optional.
ACTION_PRIORITY = ("walking", "handwaving", "boxing", "handclapping", "jogging", "running")

DIFFICULTY_TAGS = ["low_resolution", "static_camera", "staged_single_person", "out_of_cctv_domain"]

SPLIT_BY_SUBJECT = {
    "person01": "train", "person02": "train",
    "person03": "val", "person04": "val",
    "person05": "calibration", "person06": "calibration",
    **{f"person{i:02d}": "test" for i in range(7, 13)},
}

LICENSE_BLOCK = {
    "name": "KTH Actions dataset terms (publisher page)",
    "url": DATASET_PAGE,
    "spdx": "LicenseRef-KTH-noncommercial",
    "commercial_use": False,
    "redistribution": "none - clips never enter git; reproduce with bench/fetch_fixtures.py",
    "attribution": "Schuldt, Laptev and Caputo, Proc. ICPR'04, Cambridge, UK",
    "rights_basis": "publisher grants public non-commercial use with citation; quote verified at acquisition",
    "verified_quote": VERIFIED_QUOTE,
    "verified_on": VERIFIED_ON,
}

UNAVAILABLE_CATEGORIES = [
    {"category": "negative/hugging",
     "attempted_sources": ["KTH Actions (no such action class)", "RWF-2000 (videos withdrawn by author)",
                           "Hockey Fight / Movies (hosts 404; NHL/studio copyright)",
                           "XD-Violence (no licence text)", "UCF-Crime (no licence text)"],
     "why_excluded": "No lawfully available corpus isolates hugging in CCTV-like footage (WT-06 rights scan, 2026-09-29). "
                     "Gap recorded instead of fabricating labels; local consented recording required."},
    {"category": "negative/handshakes",
     "attempted_sources": ["KTH Actions (no such action class)", "RWF-2000 (withdrawn)",
                           "XD-Violence (unlicensed)", "UCF-Crime (unlicensed)"],
     "why_excluded": "Same as hugging: no lawful public CCTV source with verified licence text."},
    {"category": "negative/phone_use",
     "attempted_sources": ["KTH Actions (no such action class)", "RWF-2000 (withdrawn)",
                           "XD-Violence (unlicensed)", "UCF-Crime (unlicensed)"],
     "why_excluded": "Same as hugging: no lawful public CCTV source with verified licence text."},
    {"category": "positive/weapon_visible_close_range",
     "attempted_sources": ["public video datasets (no permissively licensed weapon video corpus verified)",
                           "image-level weapon datasets (per-dataset licence text not yet verified)"],
     "why_excluded": "No candidate passed the verify-licence-text-before-download rule yet. "
                     "Open: verify a permissively licensed image dataset for frame-level weapon evaluation."},
    {"category": "positive/violence_with_independent_onset",
     "attempted_sources": ["RWF-2000 (clip-level; withdrawn anyway)", "XD-Violence (unlicensed)",
                           "UBI-Fight / NTU-CCTV-Fight (frame-level, licence unverified [?])",
                           "KTH boxing (staged, clip-level only, no onset)"],
     "why_excluded": "No rights-cleared fixture with INDEPENDENTLY LABELED ONSET could be secured. "
                     "Consequence: time-to-detection (G-04) is UNMEASURABLE with current fixtures; "
                     "never estimated from model output."},
]


def _fetch_page(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Sentinel-Research/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("latin-1")


def verify_rights_statement():
    """Refuse acquisition unless the publisher's rights statement is still published."""
    import re
    page = _fetch_page(DATASET_PAGE)
    stripped = re.sub(r"<[^>]+>", " ", page)
    normalized = " ".join(stripped.split()).lower()
    missing = [fragment for fragment in RIGHTS_FRAGMENTS if fragment not in normalized]
    if missing:
        raise RuntimeError(
            f"Publisher rights statement changed or disappeared (missing fragments: {missing}); "
            "acquisition refused")
    return {"page": DATASET_PAGE, "quote": VERIFIED_QUOTE,
            "checked_fragments": list(RIGHTS_FRAGMENTS), "verified_on": VERIFIED_ON}


def _download(url, target, limit):
    if target.exists():
        return
    temporary = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "AI-Sentinel-Research/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as stream:
        if response.geturl().split("/")[2] != "www.csc.kth.se":
            raise ValueError("Unexpected redirect host for dataset download")
        total = 0
        deadline = time.monotonic() + 3600
        while block := response.read1(256 * 1024):
            if time.monotonic() > deadline:
                raise TimeoutError("Archive download exceeded wall-clock budget")
            total += len(block)
            if total > limit:
                raise ValueError("Archive exceeds size budget")
            stream.write(block)
    temporary.replace(target)


def media_facts(path):
    import cv2
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open extracted fixture: {path}")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()
    if not (fps > 0 and frames > 0 and width > 0 and height > 0):
        raise ValueError(f"Incomplete media facts for {path}")
    return {"fps": round(fps, 6), "frame_count": frames, "width": width, "height": height,
            "duration_s": round(frames / fps, 6)}


def select_clips(bundle):
    """One clip per subject/action: the official *_<action>_d1_uncomp.avi files."""
    wanted = {}
    for name in sorted(bundle.namelist()):
        pure = PurePosixPath(name)
        if not pure.name.endswith(f"_{SCENARIO}_uncomp.avi"):
            continue
        subject = pure.name.split("_")[0]
        if subject not in SUBJECTS:
            continue
        wanted[pure.name] = name
    return wanted


def acquire(actions, media_root):
    rights = verify_rights_statement()
    cache = media_root / "_archives"
    cache.mkdir(parents=True, exist_ok=True)
    clips_dir = media_root / "kth"
    clips_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    failures = []
    for action in actions:
        url = BASE + action + ".zip"
        archive = cache / (action + ".zip")
        try:
            _download(url, archive, ARCHIVE_LIMIT)
            archive_sha = sha256(archive)
            with zipfile.ZipFile(archive) as bundle:
                selected = select_clips(bundle)
                if not selected:
                    raise ValueError(f"No {SCENARIO} clips found for {action}")
                for filename, member in sorted(selected.items()):
                    info = bundle.getinfo(member)
                    if info.file_size > CLIP_LIMIT:
                        raise ValueError(f"Clip exceeds extraction budget: {filename}")
                    target = clips_dir / filename
                    if not target.exists():
                        target.write_bytes(bundle.read(member))
                    mapping = ACTIONS[action]
                    subject = filename.split("_")[0]
                    facts = media_facts(target)
                    entries.append({
                        "fixture_id": f"kth-{action}-{subject}",
                        "category": mapping["category"],
                        "subcategory": mapping["subcategory"],
                        "split": SPLIT_BY_SUBJECT[subject],
                        "session_id": f"kth-{subject}",
                        "media": {"path": target.relative_to(media_root).as_posix(),
                                  "sha256": sha256(target), "bytes": target.stat().st_size, **facts},
                        "source": {"dataset": "KTH Actions", "url": url,
                                   "archive_sha256": archive_sha, "retrieved": VERIFIED_ON,
                                   "publisher_page": DATASET_PAGE},
                        "license": dict(LICENSE_BLOCK),
                        "labels": {
                            "class": "benign" if mapping["category"] == "negative" else "violence_like",
                            "label_source": "publisher",
                            "annotation_ref": (
                                f"KTH publisher action label '{action}' (benign single-person action)"
                                if mapping["category"] == "negative" else
                                f"KTH publisher action label '{action}' (staged single-person punching; "
                                "no onset annotation available)"),
                            "onset_s": None,
                            "onset_available": False,
                            "frames": None,
                            "counts": None,
                            "boxes": None,
                        },
                        "difficulty_tags": list(DIFFICULTY_TAGS),
                        "notes": "Auxiliary out-of-domain fixture (160x120 static camera, staged). "
                                 "Never evidence of CCTV deployment performance.",
                    })
        except (OSError, ValueError, zipfile.BadZipFile, TimeoutError) as exc:
            failures.append({"source": url, "error": type(exc).__name__, "message": str(exc)})
    return rights, entries, failures


def build_manifest(entries, media_root, failures):
    return {
        "schema_version": "wt12-fixture-manifest/1",
        "generated": VERIFIED_ON,
        "media_root": str(media_root),
        "policy": {
            "label_provenance_allowed": ["independent-human", "publisher"],
            "label_provenance_forbidden": ["auto", "model", "pseudo", "synthetic"],
            "note": ("Labels are publisher annotations or independent human review only. "
                     "Model output and synthetic data can never establish evaluation truth."),
        },
        "runtime_contract": {
            "window_frames": 32,
            "stride_frames_policy": ("config-driven (VIOLENCE_STRIDE); the effective stride of a run is "
                                     "derivable from windows[].start_s deltas in its outputs"),
            "fps_source": "media.fps per fixture",
            "window_integrity_fields": ["valid", "frames_collected", "frames_required", "span_s"],
        },
        "split_policy": ("split by subject (= session): person01-02 train, person03-04 val, "
                         "person05-06 calibration, person07-12 test; no session crosses a split boundary"),
        "acquisition": {
            "tool": "bench/fetch_fixtures.py",
            "rights_statement_checked_at_acquisition": True,
            "failures": failures,
        },
        "fixtures": sorted(entries, key=lambda e: e["fixture_id"]),
        "unavailable_categories": UNAVAILABLE_CATEGORIES,
    }


def verify(manifest_path, media_root=None):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    root = Path(media_root or manifest["media_root"])
    problems = []
    for fixture in manifest["fixtures"]:
        path = root / fixture["media"]["path"]
        if not path.is_file():
            problems.append({"fixture_id": fixture["fixture_id"], "problem": "missing_media", "path": str(path)})
            continue
        digest = sha256(path)
        if digest != fixture["media"]["sha256"]:
            problems.append({"fixture_id": fixture["fixture_id"], "problem": "sha256_mismatch",
                             "expected": fixture["media"]["sha256"], "actual": digest})
    return problems


def main():
    parser = argparse.ArgumentParser(description="Rights-checked WT-12 fixture acquisition")
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--manifest", default=str(ROOT / "docs/campaign/eval/12-fixture-manifest.json"))
    parser.add_argument("--media-root", default=os.environ.get("SENTINEL_FIXTURE_ROOT", str(DEFAULT_MEDIA_ROOT)))
    parser.add_argument("--actions", default=",".join(ACTION_PRIORITY),
                        help="comma-separated subset of: " + ",".join(ACTION_PRIORITY))
    parser.add_argument("--write-manifest", default=None,
                        help="path to write the complete manifest (default: --manifest path)")
    args = parser.parse_args()
    media_root = Path(args.media_root)
    if args.verify:
        problems = verify(args.manifest, media_root)
        print(json.dumps({"verified_fixtures": len(json.loads(Path(args.manifest).read_text(encoding='utf-8'))["fixtures"]),
                          "problems": problems}, indent=2))
        return 0 if not problems else 1
    if not args.acquire:
        parser.error("choose --acquire or --verify")
    actions = [a for a in args.actions.split(",") if a]
    unknown = [a for a in actions if a not in ACTIONS]
    if unknown:
        parser.error(f"unknown actions: {unknown}")
    ordered = [a for a in ACTION_PRIORITY if a in actions]
    rights, entries, failures = acquire(ordered, media_root)
    manifest = build_manifest(entries, media_root, failures)
    write_json(Path(args.write_manifest or args.manifest), manifest)
    write_json(ROOT / "bench" / "fixture-acquisition-log.json",
               {"rights_check": rights, "entries": len(entries), "failures": failures,
                "media_root": str(media_root), "acquired_on": VERIFIED_ON})
    print(json.dumps({"fixtures": len(entries), "failures": failures,
                      "rights_check": rights, "media_root": str(media_root)}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
