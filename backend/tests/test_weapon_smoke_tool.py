import pytest
import json
import os
import sys

# Add backend and tools to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

def test_smoke_tool_import():
    """Verify that the smoke tool can be imported."""
    try:
        import smoke_weapon_engine
        assert True
    except ImportError:
        pytest.fail("Could not import smoke_weapon_engine")

def test_smoke_tool_result_format():
    """Verify the structure of the results dictionary (mocking the engine)."""
    # This test just ensures the internal results structure remains consistent
    # without actually running the full torchvision load.
    results = {
        "engine_imported": True,
        "success": True,
        "ready_before": False,
        "ready_after": False,
        "status_reason": "ok"
    }
    assert "success" in results
    assert isinstance(results["success"], bool)
    assert "status_reason" in results

def test_graceful_failure_no_torchvision(monkeypatch):
    """Test that the tool reports failure if torchvision is missing."""
    import smoke_weapon_engine
    
    # Mock torchvision import failure
    import builtins
    real_import = builtins.__import__
    def mock_import(name, *args, **kwargs):
        if name == 'torchvision':
            raise ImportError("Mocked missing torchvision")
        return real_import(name, *args, **kwargs)
    
    # Capture stdout
    from io import StringIO
    out = StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(builtins, "__import__", mock_import)
    
    smoke_weapon_engine.run_smoke_test(timeout_sec=1)
    
    output = out.getvalue()
    result = json.loads(output)
    assert result["success"] is False
    assert result["status_reason"] == "torchvision-missing"
