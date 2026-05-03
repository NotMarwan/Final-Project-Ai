import json
import torch
from pathlib import Path
from typing import Callable, Optional, Dict, Any, List
from torch.utils.data import Dataset

def _default_video_loader(path: str) -> torch.Tensor:
    """
    Default video loader.
    Currently, real video loading is not implemented.
    This raises NotImplementedError to prevent accidental training with mock tensors.
    For tests or dry-runs, explicitly inject a fake loader.
    """
    if not Path(path).exists():
        raise FileNotFoundError(f"Video file not found: {path}")
    
    raise NotImplementedError("Real video loading is not yet implemented. Do not use mock tensors for real training.")

class ManifestDataset(Dataset):
    """
    A manifest-aware dataset loader that reads JSONL manifests.
    Maps string labels to numeric classes and filters by split.
    """
    LABEL_MAP = {
        "normal": 0,
        "violence": 1
    }

    def __init__(
        self,
        manifest_path: str,
        split: Optional[str] = None,
        video_loader: Optional[Callable[[str], torch.Tensor]] = None,
        max_samples: Optional[int] = None
    ):
        super().__init__()
        self.manifest_path = Path(manifest_path)
        self.split = split
        self.video_loader = video_loader or _default_video_loader
        
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")

        self.entries: List[Dict[str, Any]] = []
        self._load_manifest(max_samples)

    def _load_manifest(self, max_samples: Optional[int]):
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                # Filter by split if requested
                entry_split = entry.get("split", "unknown")
                if self.split is not None and entry_split != self.split:
                    continue
                    
                # Validate label
                label_name = entry.get("label", "").lower()
                if label_name not in self.LABEL_MAP:
                    continue
                    
                self.entries.append(entry)
                
                if max_samples is not None and len(self.entries) >= max_samples:
                    break

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        entry = self.entries[idx]
        video_path = entry.get("video_path", "")
        label_name = entry.get("label", "normal").lower()
        
        try:
            tensor = self.video_loader(video_path)
        except Exception as e:
            # Handle missing files by returning a zero tensor or raising
            # Here we raise so the dataloader/collate handles it or it fails loudly in tests
            raise RuntimeError(f"Failed to load video {video_path}: {e}")

        return {
            "video": tensor,
            "label": self.LABEL_MAP[label_name],
            "label_name": label_name,
            "video_path": video_path,
            "source_dataset": entry.get("source_dataset", "unknown"),
            "split": entry.get("split", "unknown"),
        }
