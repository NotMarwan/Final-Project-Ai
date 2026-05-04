import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_manifest():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as tmp:
        tmp.write(json.dumps({"video_path": "v1.mp4", "label": "violence", "split": "train"}) + "\n")
        tmp.write(json.dumps({"video_path": "v2.mp4", "label": "normal", "split": "train"}) + "\n")
        path = tmp.name
    yield path
    if Path(path).exists():
        Path(path).unlink()

@patch("inference.ViolenceDetector")
@patch("torch.load")
def test_train_smoke_dry_run_legacy(mock_load, mock_vd, mock_manifest):
    import torch
    # Setup mock to avoid hub load
    mock_vd.return_value = MagicMock()
    
    args = [
        "--manifest", mock_manifest,
        "--dry-run",
        "--profile", "legacy_slowfast"
    ]
    
    # Capture stdout to verify behavior
    with patch("sys.stdout") as mock_stdout:
        main(args)
        
        # Verify dry-run output
        out = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        assert "Using model profile: legacy_slowfast" in out
        assert f"Video batch shape: {torch.Size([2, 3, 32, 224, 224])}" in out
        assert "Dry run complete" in out
        
    # Model should NOT be initialized for dry-run
    assert mock_vd.call_count == 0

@patch("inference.ViolenceDetector")
@patch("torch.load")
def test_train_smoke_dry_run_x3d(mock_load, mock_vd, mock_manifest):
    import torch
    args = [
        "--manifest", mock_manifest,
        "--dry-run",
        "--profile", "x3d"
    ]
    
    with patch("sys.stdout") as mock_stdout:
        main(args)
        out = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        assert "Using model profile: x3d" in out
        assert f"Video batch shape: {torch.Size([2, 3, 32, 160, 160])}" in out
        assert "Dry run complete" in out
        
    assert mock_vd.call_count == 0

def test_train_smoke_invalid_caps(mock_manifest):
    # max_train_samples > 8
    args = ["--manifest", mock_manifest, "--max-train-samples", "10", "--device", "cpu"]
    with patch("sys.stdout") as mock_stdout:
        main(args)
        out = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        assert "[ERROR] Safety cap: max_train_samples must be <= 8" in out

def test_train_smoke_invalid_epochs(mock_manifest):
    # epochs > 1
    args = ["--manifest", mock_manifest, "--epochs", "2", "--device", "cpu"]
    with patch("sys.stdout") as mock_stdout:
        main(args)
        out = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        assert "[ERROR] Safety cap: epochs must be <= 1" in out
