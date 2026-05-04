import pytest
from pathlib import Path

def test_train_config_validates_device():
    from training.train_config import TrainConfig
    config = TrainConfig(manifest_path="dummy.jsonl", device="invalid")
    with pytest.raises(ValueError) as excinfo:
        config.validate()
    assert "Invalid device" in str(excinfo.value)

def test_train_config_auto_device():
    from training.train_config import TrainConfig
    config = TrainConfig(manifest_path="dummy.jsonl", device="auto")
    config.validate()
    assert config.device in ["cpu", "cuda"]

def test_train_config_output_dir_safe_path():
    from training.train_config import TrainConfig
    config = TrainConfig(manifest_path="dummy.jsonl", output_dir="bad_dir/")
    with pytest.raises(ValueError) as excinfo:
        config.validate()
    assert "output_dir must be under .runlogs/training" in str(excinfo.value)

def test_train_config_no_overwrite_best_model():
    from training.train_config import TrainConfig
    config = TrainConfig(
        manifest_path="dummy.jsonl",
        weights_path="backend/best_model.pt",
        output_dir=".runlogs/training/best_model.pt"
    )
    with pytest.raises(ValueError) as excinfo:
        config.validate()
    assert "cannot overwrite backend/best_model.pt directly" in str(excinfo.value)

def test_train_config_appends_timestamp():
    from training.train_config import TrainConfig
    config = TrainConfig(manifest_path="dummy.jsonl", output_dir=".runlogs/training/smoke")
    config.validate()
    assert "run_" in config.output_dir
    assert config.output_dir.replace("\\", "/").startswith(".runlogs/training")
