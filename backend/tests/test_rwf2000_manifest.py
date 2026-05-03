import os
import json
import pytest
import tempfile
from pathlib import Path
from backend.tools.build_rwf2000_manifest import build_manifest

def test_build_manifest():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create mock structure
        (tmp_path / "train" / "Fight").mkdir(parents=True)
        (tmp_path / "train" / "NonFight").mkdir(parents=True)
        (tmp_path / "val" / "Fight").mkdir(parents=True)
        (tmp_path / "val" / "NonFight").mkdir(parents=True)
        
        # Create dummy videos
        (tmp_path / "train" / "Fight" / "v1.mp4").touch()
        (tmp_path / "train" / "NonFight" / "v2.mp4").touch()
        (tmp_path / "val" / "Fight" / "v3.mp4").touch()
        (tmp_path / "val" / "NonFight" / "v4.mp4").touch()
        
        manifest_path = tmp_path / "manifest.jsonl"
        
        build_manifest(str(tmp_path), str(manifest_path))
        
        assert manifest_path.exists()
        
        with open(manifest_path, "r") as f:
            lines = f.readlines()
            
        assert len(lines) == 4
        
        entries = [json.loads(line) for line in lines]
        
        # Verify mapping
        violence_entries = [e for e in entries if e["label"] == "violence"]
        normal_entries = [e for e in entries if e["label"] == "normal"]
        
        assert len(violence_entries) == 2
        assert len(normal_entries) == 2
        
        # Verify splits
        train_entries = [e for e in entries if e["split"] == "train"]
        val_entries = [e for e in entries if e["split"] == "val"]
        
        assert len(train_entries) == 2
        assert len(val_entries) == 2
        
        # Verify source
        assert all(e["source_dataset"] == "rwf2000_kaggle" for e in entries)
