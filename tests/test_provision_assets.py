"""Failed provisioning must never expose corrupt weights to the runtime."""
import hashlib
from pathlib import Path

import pytest

from scripts import provision_assets as assets


@pytest.fixture
def setup_assets(tmp_path, monkeypatch):
    root = tmp_path / "project"
    source = tmp_path / "source"
    source.mkdir()
    content = b"verified model bytes"
    relative = "backend/models/fixture.onnx"
    spec = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    monkeypatch.setattr(assets, "ROOT", root)
    monkeypatch.setattr(assets, "ASSETS", {relative: spec})
    monkeypatch.setattr(assets, "FIXTURE_MANIFEST", root / "manifest.json")
    (source / "fixture.onnx").write_bytes(content)
    return root, source, relative, content


def test_verified_copy_is_published_and_rerun_is_idempotent(setup_assets):
    root, source, relative, content = setup_assets
    assert assets.provision(str(source)) == 0
    assert (root / relative).read_bytes() == content
    assert assets.provision(str(source)) == 0
    assert not list(root.rglob("*.part"))


def test_hash_mismatch_never_publishes_model(setup_assets):
    root, source, relative, content = setup_assets
    (source / "fixture.onnx").write_bytes(b"x" * len(content))
    assert assets.provision(str(source)) == 1
    assert not (root / relative).exists()
    assert not list(root.rglob("*.part"))


def test_oversized_source_is_rejected_and_retained(setup_assets):
    root, source, relative, content = setup_assets
    oversized = content + b"extra"
    (source / "fixture.onnx").write_bytes(oversized)
    assert assets.provision(str(source)) == 1
    assert not (root / relative).exists()
    assert (source / "fixture.onnx").read_bytes() == oversized
    assert not list(root.rglob("*.part"))


def test_existing_wrong_weight_is_never_overwritten(setup_assets):
    root, source, relative, _ = setup_assets
    target = root / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"user's existing checkpoint")
    assert assets.provision(str(source)) == 1
    assert target.read_bytes() == b"user's existing checkpoint"


def test_transfer_failure_removes_only_temporary_file(setup_assets, monkeypatch, capsys):
    root, _, relative, _ = setup_assets
    def fail(*args, **kwargs):
        raise OSError("https://credential@example.invalid")
    monkeypatch.setattr(assets.urllib.request, "urlopen", fail)
    assert assets.provision("https://credential@example.invalid") == 1
    assert not (root / relative).exists()
    assert not list(root.rglob("*.part"))
    assert "credential" not in capsys.readouterr().out
