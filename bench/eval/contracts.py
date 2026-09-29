"""Evaluation contracts for WT-12: fixture manifest and recorded-output validation.

Discipline enforced here (campaign rules + docs/campaign/eval/12-eval-protocol.md):
- Label provenance must be `publisher` or `independent-human`. Model output,
  pseudo-labels and synthetic labels can NEVER establish evaluation truth.
- Split leakage prevention: media SHA-256 must be unique across all fixtures and
  all clips of one session must sit in a single split.
- Recorded outputs must reference a manifest fixture whose source SHA-256 matches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

HEX64 = re.compile(r"^[a-f0-9]{64}$")
SPLITS = {"train", "val", "calibration", "test", "regression-only"}
ALLOWED_LABEL_SOURCES = {"publisher", "independent-human"}
FORBIDDEN_LABEL_SOURCES = {"model", "pseudo", "synthetic", "auto"}
CATEGORIES = {"negative", "positive"}
ONSET_LABELS = {"violence_like", "weapon", "violence"}


class ContractError(ValueError):
    """A fixture, label or output record violates the evaluation contract."""


def _require(condition, message):
    if not condition:
        raise ContractError(message)


def _check_hash(value, where):
    _require(isinstance(value, str) and HEX64.fullmatch(value), f"{where}: sha256 must be 64 lowercase hex chars")


def _check_number(value, where, minimum=None, allow_none=False):
    if value is None and allow_none:
        return
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{where}: must be a number")
    _require(value == value and abs(value) != float("inf"), f"{where}: must be finite")
    if minimum is not None:
        _require(value >= minimum, f"{where}: must be >= {minimum}")


def validate_fixture(fixture, seen_ids, seen_hashes, seen_sessions):
    where = f"fixture {fixture.get('fixture_id', '<missing>')!r}"
    fixture_id = fixture.get("fixture_id")
    _require(isinstance(fixture_id, str) and fixture_id, f"{where}: fixture_id is required")
    _require(fixture_id not in seen_ids, f"{where}: duplicate fixture_id")
    seen_ids.add(fixture_id)

    _require(fixture.get("category") in CATEGORIES, f"{where}: category must be one of {sorted(CATEGORIES)}")
    _require(isinstance(fixture.get("subcategory"), str) and fixture["subcategory"], f"{where}: subcategory is required")
    split = fixture.get("split")
    _require(split in SPLITS, f"{where}: split must be one of {sorted(SPLITS)}")
    session = fixture.get("session_id")
    _require(isinstance(session, str) and session, f"{where}: session_id is required for leakage control")
    prior_split = seen_sessions.setdefault(session, split)
    _require(prior_split == split,
             f"{where}: session {session!r} straddles splits ({prior_split!r} vs {split!r}); "
             "split by session, never by clip within a session")

    media = fixture.get("media")
    _require(isinstance(media, dict), f"{where}: media block is required")
    _require(isinstance(media.get("path"), str) and media["path"], f"{where}: media.path is required")
    _check_hash(media.get("sha256"), f"{where}: media.sha256")
    _require(media["sha256"] not in seen_hashes,
             f"{where}: media.sha256 duplicates another fixture; duplicated content leaks across splits")
    seen_hashes.add(media["sha256"])
    _check_number(media.get("bytes"), f"{where}: media.bytes", minimum=1)
    _check_number(media.get("duration_s"), f"{where}: media.duration_s", minimum=0.01)
    _check_number(media.get("fps"), f"{where}: media.fps", minimum=0.01)
    _check_number(media.get("width"), f"{where}: media.width", minimum=1)
    _check_number(media.get("height"), f"{where}: media.height", minimum=1)
    _check_number(media.get("frame_count"), f"{where}: media.frame_count", minimum=1, allow_none=True)

    source = fixture.get("source")
    _require(isinstance(source, dict), f"{where}: source block is required")
    _require(isinstance(source.get("url"), str) and source["url"], f"{where}: source.url is required")
    _require(isinstance(source.get("dataset"), str) and source["dataset"], f"{where}: source.dataset is required")
    _require(isinstance(source.get("retrieved"), str) and source["retrieved"], f"{where}: source.retrieved is required")
    if source.get("archive_sha256") is not None:
        _check_hash(source["archive_sha256"], f"{where}: source.archive_sha256")

    license_block = fixture.get("license")
    _require(isinstance(license_block, dict), f"{where}: license block is required (rights check is binding)")
    for key in ("name", "rights_basis", "verified_on"):
        _require(isinstance(license_block.get(key), str) and license_block[key],
                 f"{where}: license.{key} is required")
    for key in ("commercial_use", "redistribution"):
        _require(key in license_block, f"{where}: license.{key} is required (explicit, even if null is not allowed)")
    _require(license_block.get("commercial_use") in (True, False), f"{where}: license.commercial_use must be boolean")
    _require(isinstance(license_block.get("redistribution"), str) and license_block["redistribution"],
             f"{where}: license.redistribution must state the redistribution position")

    labels = fixture.get("labels")
    _require(isinstance(labels, dict), f"{where}: labels block is required")
    label_source = labels.get("label_source")
    _require(label_source in ALLOWED_LABEL_SOURCES,
             f"{where}: labels.label_source must be one of {sorted(ALLOWED_LABEL_SOURCES)}; "
             f"got {label_source!r}")
    _require(label_source not in FORBIDDEN_LABEL_SOURCES, f"{where}: model/pseudo/synthetic labels cannot be truth")
    _require(isinstance(labels.get("class"), str) and labels["class"], f"{where}: labels.class is required")
    if fixture["category"] == "negative":
        _require(labels["class"] == "benign", f"{where}: negative fixture must carry labels.class 'benign'")
    else:
        _require(labels["class"] != "benign", f"{where}: positive fixture must not carry labels.class 'benign'")
    _require(isinstance(labels.get("annotation_ref"), str) and labels["annotation_ref"],
             f"{where}: labels.annotation_ref must cite the annotation source")

    onset = labels.get("onset_s")
    _check_number(onset, f"{where}: labels.onset_s", minimum=0, allow_none=True)
    _require(isinstance(labels.get("onset_available"), bool), f"{where}: labels.onset_available must be boolean")
    _require(labels["onset_available"] == (onset is not None),
             f"{where}: labels.onset_available must agree with labels.onset_s presence")
    if onset is not None:
        _require(onset <= media["duration_s"], f"{where}: labels.onset_s lies beyond media.duration_s")
        _require(labels["class"] in ONSET_LABELS, f"{where}: onset labels only make sense on violence/weapon classes")

    for frame in labels.get("frames") or []:
        _check_number(frame.get("start_s"), f"{where}: labels.frames.start_s", minimum=0)
        _check_number(frame.get("end_s"), f"{where}: labels.frames.end_s", minimum=0)
        _require(frame["end_s"] > frame["start_s"], f"{where}: labels.frames interval must be non-empty")
        _require(frame["end_s"] <= media["duration_s"] + 1e-6, f"{where}: labels.frames interval exceeds duration")
        _require(isinstance(frame.get("label"), str) and frame["label"], f"{where}: labels.frames.label is required")

    for box in labels.get("boxes") or []:
        _check_number(box.get("frame_time_s"), f"{where}: labels.boxes.frame_time_s", minimum=0)
        _require(box["frame_time_s"] <= media["duration_s"] + 1e-6,
                 f"{where}: labels.boxes.frame_time_s exceeds duration")
        _require(isinstance(box.get("class"), str) and box["class"], f"{where}: labels.boxes.class is required")
        bbox = box.get("bbox")
        _require(isinstance(bbox, list) and len(bbox) == 4 and
                 all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox),
                 f"{where}: labels.boxes.bbox must be four numbers")
        _require(bbox[2] > bbox[0] and bbox[3] > bbox[1], f"{where}: labels.boxes.bbox must be non-empty")

    counts = labels.get("counts")
    if counts is not None:
        _require(isinstance(counts, dict), f"{where}: labels.counts must be an object")
        for key in ("visible_persons", "unique_persons", "events"):
            _require(key in counts, f"{where}: labels.counts.{key} is required when counts are present")
        _require(isinstance(counts["visible_persons"], list) and
                 all(isinstance(v, int) and v >= 0 for v in counts["visible_persons"]),
                 f"{where}: labels.counts.visible_persons must be a list of non-negative integers")
        _require(isinstance(counts["unique_persons"], int) and counts["unique_persons"] >= 0,
                 f"{where}: labels.counts.unique_persons must be a non-negative integer")
        _require(isinstance(counts["events"], int) and counts["events"] >= 0,
                 f"{where}: labels.counts.events must be a non-negative integer")
        _require(len(counts["visible_persons"]) == len(counts.get("sample_times_s") or []),
                 f"{where}: labels.counts.visible_persons needs an equally long sample_times_s list")

    tags = fixture.get("difficulty_tags")
    _require(isinstance(tags, list) and all(isinstance(t, str) and t for t in tags),
             f"{where}: difficulty_tags must be a list of non-empty strings")
    return fixture


def load_manifest(path):
    raw = Path(path).read_text(encoding="utf-8")
    manifest = json.loads(raw)
    _require(manifest.get("schema_version", "").startswith("wt12-fixture-manifest/"),
             "manifest schema_version must be 'wt12-fixture-manifest/<version>'")
    _require(isinstance(manifest.get("media_root"), str) and manifest["media_root"],
             "manifest media_root must declare where the large media live (media stay out of git)")
    policy = manifest.get("policy")
    _require(isinstance(policy, dict), "manifest policy block is required")
    _require(policy.get("label_provenance_allowed") == sorted(ALLOWED_LABEL_SOURCES),
             "manifest policy must state the allowed label provenance exactly")
    _require(policy.get("label_provenance_forbidden") == sorted(FORBIDDEN_LABEL_SOURCES),
             "manifest policy must state the forbidden label provenance exactly")
    fixtures = manifest.get("fixtures")
    _require(isinstance(fixtures, list), "manifest fixtures must be a list (may be empty)")
    seen_ids, seen_hashes, seen_sessions = set(), set(), {}
    for fixture in fixtures:
        validate_fixture(fixture, seen_ids, seen_hashes, seen_sessions)
    for gap in manifest.get("unavailable_categories") or []:
        for key in ("category", "attempted_sources", "why_excluded"):
            _require(isinstance(gap.get(key), (str, list)) and gap[key],
                     f"unavailable_categories entry missing {key!r}")
    manifest["_path"] = str(Path(path))
    manifest["_by_id"] = {f["fixture_id"]: f for f in fixtures}
    return manifest


def verify_media_hashes(manifest, media_root=None):
    """Hash-check the on-disk media against the manifest. Returns a list of problems."""
    root = Path(media_root or manifest["media_root"])
    problems = []
    for fixture in manifest["fixtures"]:
        media = fixture["media"]
        path = root / media["path"]
        if not path.is_file():
            problems.append({"fixture_id": fixture["fixture_id"], "problem": "missing_media", "path": str(path)})
            continue
        digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        if digest != media["sha256"]:
            problems.append({"fixture_id": fixture["fixture_id"], "problem": "sha256_mismatch",
                             "expected": media["sha256"], "actual": digest, "path": str(path)})
    return problems


def load_outputs(manifest, outputs):
    """Load recorded model outputs (one JSON per fixture or one JSON list).

    `outputs` may be a comma-separated list of directories/files (e.g. the two
    anchor passes); records for the same fixture_id are MERGED (row lists
    concatenated in source order, scalar fields must agree). Every record must
    reference a manifest fixture and carry the fixture's source SHA-256 so a run
    cannot silently score different media than the manifest names.
    """
    sources = [Path(item.strip()) for item in str(outputs).split(",") if item.strip()]
    records = []
    for source in sources:
        if source.is_dir():
            files = sorted(source.glob("*.json"))
            for file in files:
                payload = json.loads(file.read_text(encoding="utf-8"))
                records.extend(payload if isinstance(payload, list) else [payload])
        else:
            payload = json.loads(source.read_text(encoding="utf-8"))
            records = payload if isinstance(payload, list) else payload.get("outputs", [payload])
    validated = []
    for record in records:
        fixture_id = record.get("fixture_id")
        _require(fixture_id in manifest["_by_id"], f"output references unknown fixture_id {fixture_id!r}")
        fixture = manifest["_by_id"][fixture_id]
        _require(record.get("source_sha256") == fixture["media"]["sha256"],
                 f"output for {fixture_id!r} carries source_sha256 {record.get('source_sha256')!r} "
                 f"but the manifest names {fixture['media']['sha256']}")
        _require(record.get("source_mode") in {"file-media", "webcam-synthetic", "live"},
                 f"output for {fixture_id!r} must declare source_mode (file-media/webcam-synthetic/live)")
        _require(record["source_mode"] != "live",
                 "no camera device exists in this environment; a 'live' source_mode record cannot be accepted")
        for key in ("windows", "detections", "alerts", "tracks"):
            _require(isinstance(record.get(key, []), list), f"output for {fixture_id!r}: {key} must be a list")
        for window in record.get("windows", []):
            _check_number(window.get("start_s"), f"{fixture_id}: window.start_s", minimum=0)
            _check_number(window.get("end_s"), f"{fixture_id}: window.end_s", minimum=0)
            _require(window["end_s"] > window["start_s"], f"{fixture_id}: window interval must be non-empty")
            _check_number(window.get("violence_conf"), f"{fixture_id}: window.violence_conf", minimum=0)
            _require(0 <= window["violence_conf"] <= 1, f"{fixture_id}: window.violence_conf must be in [0,1]")
        for alert in record.get("alerts", []):
            _require(isinstance(alert.get("alert_id"), str) and alert["alert_id"],
                     f"{fixture_id}: alert.alert_id is required")
            _check_number(alert.get("time_s"), f"{fixture_id}: alert.time_s", minimum=0)
            _check_number(alert.get("score"), f"{fixture_id}: alert.score", minimum=0)
        for det in record.get("detections", []):
            _check_number(det.get("time_s"), f"{fixture_id}: detection.time_s", minimum=0)
            _require(isinstance(det.get("class"), str) and det["class"],
                     f"{fixture_id}: detection.class is required")
            _check_number(det.get("score"), f"{fixture_id}: detection.score", minimum=0)
        for row in record.get("tracks", []):
            _check_number(row.get("time_s"), f"{fixture_id}: track.time_s", minimum=0)
            _require(isinstance(row.get("track_id"), (int, str)) and str(row.get("track_id")),
                     f"{fixture_id}: track.track_id is required")
        validated.append(record)
    merged = {}
    for record in validated:
        fixture_id = record["fixture_id"]
        if fixture_id not in merged:
            merged[fixture_id] = dict(record)
            continue
        target = merged[fixture_id]
        run_ids = {target.get("run_id"), record.get("run_id")}
        for key, value in record.items():
            if key == "run_id":
                continue
            if key in ("windows", "detections", "alerts", "tracks"):
                target[key] = list(target.get(key, [])) + list(value)
            elif key in target and target[key] != value:
                raise ContractError(
                    f"conflicting field {key!r} across passes for {fixture_id!r}; "
                    "passes of one anchor must agree on scalars")
            else:
                target[key] = value
        target["run_ids"] = sorted(str(r) for r in run_ids if r)
    return [merged[key] for key in sorted(merged)]


def main():
    parser = argparse.ArgumentParser(description="Validate a WT-12 fixture manifest")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--verify-media", action="store_true", help="also hash-check media under media_root")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    result = {"fixtures": len(manifest["fixtures"]), "status": "ok",
              "unavailable_categories": len(manifest.get("unavailable_categories") or [])}
    if args.verify_media:
        problems = verify_media_hashes(manifest)
        result["media_problems"] = problems
        result["status"] = "ok" if not problems else "media_mismatch"
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
