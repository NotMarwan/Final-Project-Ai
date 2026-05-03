import pytest
import torch
from datasets.video_contract import LEGACY_SLOWFAST_PROFILE, X3D_PROFILE, get_profile

def test_contract_profiles_exist():
    assert LEGACY_SLOWFAST_PROFILE.name == "legacy_slowfast"
    assert X3D_PROFILE.name == "x3d"
    
def test_legacy_slowfast_contract():
    p = LEGACY_SLOWFAST_PROFILE
    assert p.num_frames == 32
    assert p.resolution == 224
    assert p.resize_size == 224
    assert p.model_class == "ViolenceDetector"

def test_x3d_contract():
    p = X3D_PROFILE
    assert p.num_frames == 32
    assert p.resolution == 160
    assert p.resize_size == 182
    assert p.model_class == "X3DViolenceModel"

def test_get_profile():
    assert get_profile("legacy_slowfast") == LEGACY_SLOWFAST_PROFILE
    assert get_profile("x3d") == X3D_PROFILE
    with pytest.raises(ValueError):
        get_profile("unknown")
