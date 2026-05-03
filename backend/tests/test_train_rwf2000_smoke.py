import pytest
import json
import tempfile
from pathlib import Path
import subprocess
import sys

@pytest.fixture
def mock_manifest():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as tmp:
        tmp.write(json.dumps({"video_path": "v1.mp4", "label": "violence", "split": "train"}) + "\n")
        tmp.write(json.dumps({"video_path": "v2.mp4", "label": "normal", "split": "train"}) + "\n")
        path = tmp.name
    yield path
    if Path(path).exists():
        Path(path).unlink()

def test_train_smoke_dry_run_legacy(mock_manifest):
    cmd = [
        sys.executable, "backend/tools/train_rwf2000_smoke.py",
        "--manifest", mock_manifest,
        "--dry-run",
        "--profile", "legacy_slowfast"
    ]
    env = {"PYTHONPATH": "backend"}
    result = subprocess.run(cmd, env={**os.environ, **env}, capture_output=True, text=True)
    assert result.returncode == 0
    assert "Using model profile: legacy_slowfast" in result.stdout
    assert "Video batch shape: torch.Size([2, 3, 32, 224, 224])" in result.stdout
    assert "Dry run complete" in result.stdout

def test_train_smoke_dry_run_x3d(mock_manifest):
    cmd = [
        sys.executable, "backend/tools/train_rwf2000_smoke.py",
        "--manifest", mock_manifest,
        "--dry-run",
        "--profile", "x3d"
    ]
    env = {"PYTHONPATH": "backend"}
    result = subprocess.run(cmd, env={**os.environ, **env}, capture_output=True, text=True)
    assert result.returncode == 0
    assert "Using model profile: x3d" in result.stdout
    assert "Video batch shape: torch.Size([2, 3, 32, 160, 160])" in result.stdout
    assert "Dry run complete" in result.stdout

import os
