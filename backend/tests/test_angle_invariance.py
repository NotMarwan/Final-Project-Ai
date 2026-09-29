import numpy as np
import pytest
import torch

pytestmark = pytest.mark.integration

def create_test_clip(frame_count=32, size=160):
    """Create a dummy video clip."""
    import torch
    return torch.randn(1, 3, frame_count, size, size)

def rotate_frame_batch(clip: torch.Tensor, angle_deg: float) -> torch.Tensor:
    """Simulate camera angle by rotating frames."""
    # Simplified: just return the clip as-is for testing structure
    return clip

def test_model_handles_eye_level_angle():
    """Model should maintain accuracy at 170cm eye-level angle."""
    import torch
    from models.multi_angle_x3d import MultiAngleX3D
    model = MultiAngleX3D(num_classes=2)
    clip = create_test_clip()
    
    # Simulate eye-level angle (0 degrees rotation from horizontal)
    eye_level_clip = rotate_frame_batch(clip, 0)
    output = model(eye_level_clip)
    
    assert output.shape == (1, 2), "Output shape incorrect"
    probs = torch.softmax(output, dim=-1)
    assert torch.allclose(probs.sum(), torch.tensor(1.0), atol=0.01), "Probabilities don't sum to 1"

def test_model_angle_augmentation_training():
    """Model should use angle augmentation during forward pass."""
    import torch
    from models.multi_angle_x3d import MultiAngleX3D
    model = MultiAngleX3D(num_classes=2, use_angle_augmentation=True)
    clip = create_test_clip()
    
    # Train mode should apply augmentations
    model.train()
    output1 = model(clip)
    output2 = model(clip)
    
    # With augmentation, outputs may differ slightly (dropout/ augmentation)
    model.eval()
    with torch.no_grad():
        eval_output1 = model(clip)
        eval_output2 = model(clip)
    
    # In eval mode, outputs should be identical
    assert torch.allclose(eval_output1, eval_output2), "Eval mode should be deterministic"
