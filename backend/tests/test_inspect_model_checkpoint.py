import pytest
import torch
import tempfile
from pathlib import Path
from tools.inspect_model_checkpoint import inspect_checkpoint, verify_compatibility

def test_inspect_checkpoint_safe_load(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        weights_path = Path(tmpdir) / "test.pt"
        # Create a fake state dict
        fake_sd = {
            "model.layer1.weight": torch.randn(10, 10),
            "model.layer1.bias": torch.randn(10),
        }
        torch.save(fake_sd, weights_path)
        
        inspect_checkpoint(str(weights_path))
        
        captured = capsys.readouterr()
        assert "CHECKPOINT INSPECTION: test.pt" in captured.out
        assert "Type: <class 'dict'>" in captured.out
        assert "Tensor count: 2" in captured.out
        assert "model.layer1.weight" in captured.out

def test_inspect_checkpoint_missing_file(capsys):
    inspect_checkpoint("non_existent.pt")
    captured = capsys.readouterr()
    assert "[ERROR] File not found" in captured.out

def test_test_compatibility_mock(capsys, monkeypatch):
    # Mocking inference imports to avoid heavy dependencies in simple unit test
    class MockModel:
        def __init__(self, **kwargs):
            self.params = {}
        def to(self, device):
            return self
        def eval(self):
            pass
        def load_state_dict(self, sd, strict=True):
            missing = ["missing.key"]
            unexpected = ["unexpected.key"]
            return missing, unexpected
        def state_dict(self):
            return {}

    # Mock the imports in the tool
    import inference
    monkeypatch.setattr("inference.X3DViolenceModel", MockModel)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        weights_path = Path(tmpdir) / "test.pt"
        torch.save({"state_dict": {}}, weights_path)
        
        verify_compatibility(str(weights_path), "X3DViolenceModel")
        
        captured = capsys.readouterr()
        assert "COMPATIBILITY TEST: X3DViolenceModel" in captured.out
        assert "Missing keys:    1" in captured.out
        assert "Unexpected keys: 1" in captured.out
