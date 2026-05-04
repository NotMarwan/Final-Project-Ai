from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import time

@dataclass
class TrainConfig:
    manifest_path: str
    output_dir: str = ".runlogs/training/"
    weights_path: str = "backend/best_model.pt"
    batch_size: int = 4
    epochs: int = 1
    learning_rate: float = 1e-4
    device: str = "auto"
    num_workers: int = 0
    seed: int = 42
    max_train_samples: Optional[int] = None
    max_val_samples: Optional[int] = None
    freeze_backbone: bool = True

    def validate(self):
        """Validate configuration rules."""
        # Device validation
        if self.device not in ["cpu", "cuda", "auto"]:
            raise ValueError(f"Invalid device: {self.device}. Must be cpu, cuda, or auto.")
        if self.device == "auto":
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # Safe output directory validation
        out_path = Path(self.output_dir)
        if not str(out_path).replace("\\", "/").startswith(".runlogs/training"):
            # Also allow absolute path that ends in .runlogs/training
            if ".runlogs/training" not in str(out_path).replace("\\", "/"):
                raise ValueError("output_dir must be under .runlogs/training/ to prevent tracked checkpoints.")
        
        # Prevent overwriting best_model.pt directly as output
        if Path(self.weights_path).name == "best_model.pt" and str(out_path.name) == "best_model.pt":
            raise ValueError("output_dir cannot overwrite backend/best_model.pt directly.")

        # Ensure output directory has a timestamp/run name
        if "run_" not in out_path.name:
            self.output_dir = str(out_path / f"run_{int(time.time())}")
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        else:
            out_path.mkdir(parents=True, exist_ok=True)
