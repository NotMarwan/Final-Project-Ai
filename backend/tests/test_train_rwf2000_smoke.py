import pytest
import subprocess
import json
import tempfile
from pathlib import Path
import os

@pytest.fixture
def fake_manifest():
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = Path(tmpdir) / "test_manifest.jsonl"
        # We need to create dummy videos for the smoke train to load, 
        # or use the dry-run which initializes the dataset but we'll mock video loading
        # Wait, train_rwf2000_smoke uses ManifestDataset without passing video_loader.
        # So it will hit the default loader, which throws FileNotFoundError if missing.
        # So we MUST create empty files that act as videos to pass the Path.exists() check.
        
        video1 = Path(tmpdir) / "fake1.mp4"
        video2 = Path(tmpdir) / "fake2.mp4"
        video1.touch()
        video2.touch()
        
        entries = [
            {"video_path": str(video1), "label": "violence", "split": "train"},
            {"video_path": str(video2), "label": "normal", "split": "val"},
        ]
        with open(manifest_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        yield manifest_path

def test_train_smoke_dry_run(fake_manifest):
    # Run the smoke tool with --dry-run
    # We use subprocess to test the CLI
    
    # We need to set PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    
    cmd = [
        "python", "backend/tools/train_rwf2000_smoke.py",
        "--manifest", str(fake_manifest),
        "--dry-run"
    ]
    
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "[DRY RUN] Validating data loader only..." in result.stdout
    assert "Successfully loaded one train item" in result.stdout
    assert "[DRY RUN] Completed successfully" in result.stdout

def test_train_smoke_aborts_without_dry_run(fake_manifest):
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    
    cmd = [
        "python", "backend/tools/train_rwf2000_smoke.py",
        "--manifest", str(fake_manifest)
    ]
    
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "[WARN] Actual model training loop is not yet integrated" in result.stdout
    assert "Please use --dry-run for infrastructure validation" in result.stdout

def test_train_smoke_real_loader(fake_manifest):
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    
    cmd = [
        "python", "backend/tools/train_rwf2000_smoke.py",
        "--manifest", str(fake_manifest),
        "--dry-run",
        "--real-loader"
    ]
    
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    
    # It should fail to decode the empty fake.mp4
    assert result.returncode != 0
    assert "0 frames or is corrupt" in result.stdout or "Failed to load video" in result.stdout
