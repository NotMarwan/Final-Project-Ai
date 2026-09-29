"""Provision the campaign's declared external assets for a fresh clone.

The ONNX weights and the KTH fixtures are NOT committed (policy: no weights/large
media in git). This script fetches/copies them and verifies the recorded SHA-256
before publishing the two ONNX files. The violence checkpoint, optional face
weights and calibration artifact are separate startup requirements.

Existing assets are never overwritten. Failed or mismatched downloads are never
published at a runtime model path; only verified temporary files are linked in.

Usage:
    py scripts/provision_assets.py --source <dir-or-URL-prefix>   # copy or fetch
    py scripts/provision_assets.py --check                        # verify only
"""
from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Declared external assets (hash-verified). Sources are operator-supplied: the
# campaign recorded the hashes, not a redistribution URL, for the ONNX pair.
ASSETS: dict[str, dict[str, object]] = {
    "backend/models/person_yolo.onnx": {
        "sha256": "3fafb13e995667e7f877c647b33df05be6d587e75aa79d9cc34e9b3f493e60b8",
        "bytes": 12_851_087,
        "fetch": True,
    },
    "backend/models/weapon_yolo.onnx": {
        "sha256": "96991cd5d5dbeb7e8d439b3e5b75517bc8c55ea4ac740ec5bc8491d545875aef",
        "bytes": 103_636_665,
        "fetch": True,
    },
}

# KTH fixtures: expected at C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-12-fixtures/
# per docs/campaign/eval/12-fixture-manifest.json (36 clips; hashes in the manifest).
FIXTURE_MANIFEST = ROOT / "docs" / "campaign" / "eval" / "12-fixture-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_path(path: Path, relative: str, spec: dict[str, object]) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"missing: {relative}"
    actual = sha256(path)
    if actual != spec["sha256"]:
        return False, f"hash mismatch: {relative} expected {spec['sha256']} got {actual}"
    size = spec.get("bytes")
    if isinstance(size, int) and path.stat().st_size != size:
        return False, f"size mismatch: {relative} expected {size} got {path.stat().st_size}"
    return True, f"ok: {relative}"


def verify(relative: str, spec: dict[str, object]) -> tuple[bool, str]:
    return _verify_path(ROOT / relative, relative, spec)


def _stage_asset(source: str, relative: str, spec: dict[str, object]) -> None:
    """Publish verified bytes without replacing an existing or concurrent asset."""
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    expected_size = int(spec["bytes"])
    fd, temporary_name = tempfile.mkstemp(prefix=".provision-", suffix=".part", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as destination:
            if source.startswith(("http://", "https://")):
                remote = source.rstrip("/") + "/" + Path(relative).name
                origin = urllib.request.urlopen(remote, timeout=60)  # explicit operator source
            else:
                origin = (Path(source) / Path(relative).name).open("rb")
            with origin:
                copied = 0
                while chunk := origin.read(min(1 << 20, expected_size - copied + 1)):
                    copied += len(chunk)
                    if copied > expected_size:
                        raise ValueError("asset exceeds declared size")
                    destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        ok, _ = _verify_path(temporary, relative, spec)
        if not ok:
            raise ValueError("asset failed integrity verification")
        # Both names are on the same filesystem. Linking is atomic and fails if
        # another writer created the target; unlike replace(), it cannot clobber it.
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def provision(source: str | None) -> int:
    failures = 0
    for relative, spec in ASSETS.items():
        target = ROOT / relative
        if not target.exists():
            if not source:
                print(f"missing (no source): {relative}")
                failures += 1
                continue
            try:
                _stage_asset(source, relative, spec)
            except FileExistsError:
                # A concurrent publication must pass the same integrity check.
                pass
            except (OSError, ValueError):
                # Do not print an operator-supplied URL or exception containing
                # credentials. Existing source and destination files are retained.
                print(f"provision failed: {relative} (transfer or integrity error)")
                failures += 1
                continue
        ok, message = verify(relative, spec)
        print(message)
        failures += 0 if ok else 1
    if FIXTURE_MANIFEST.is_file():
        print("Fixture manifest available; media and additional startup assets require separate verification.")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="directory or URL prefix holding the declared assets")
    parser.add_argument("--check", action="store_true", help="verify only, do not copy/fetch")
    args = parser.parse_args()
    if args.check:
        failures = sum(0 if verify(name, spec)[0] else 1 for name, spec in ASSETS.items())
        for name, spec in ASSETS.items():
            print(verify(name, spec)[1])
        return 1 if failures else 0
    return provision(args.source)


if __name__ == "__main__":
    raise SystemExit(main())
