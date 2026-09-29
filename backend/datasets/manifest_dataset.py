import json
import torch
from torch.utils.data import Dataset
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Union
from .video_loader import load_video_clip
from .video_contract import DEFAULT_PROFILE, ModelProfile, get_profile

class ManifestDataset(Dataset):
    """
    Dataset that loads video clips based on a JSONL manifest.
    
    Manifest format:
    {"video_path": "path/to/video.mp4", "label": "violence"|"normal", "split": "train"|"val"}
    """
    def __init__(
        self,
        manifest_path: str,
        split: Optional[str] = None,
        profile: Union[str, ModelProfile] = DEFAULT_PROFILE,
        transform: Optional[Callable] = None,
        loader_fn: Optional[Callable] = None,  # For testing injection
    ):
        self.manifest_path = Path(manifest_path)
        self.split = split
        self.profile = get_profile(profile) if isinstance(profile, str) else profile
        self.transform = transform
        self.loader_fn = loader_fn or load_video_clip
        
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_path}")
            
        self.samples = self._load_manifest()
        
        # Label mapping: 0=normal, 1=violence
        self.label_map = {"normal": 0, "violence": 1}

    def _load_manifest(self):
        samples = []
        with open(self.manifest_path, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                item = json.loads(line)
                if self.split and item.get("split") != self.split:
                    continue
                samples.append(item)
        return samples

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        item = self.samples[idx]
        # Support both 'video_path' and 'video' keys
        video_path = item.get("video_path") or item.get("video")
        label_str = item.get("label")
        
        if not video_path:
            raise KeyError(f"Sample at index {idx} missing video path in manifest.")
            
        # Real loader will use the configured profile
        video_tensor = self.loader_fn(video_path, profile=self.profile)
        
        if self.transform:
            video_tensor = self.transform(video_tensor)
            
        label = self.label_map.get(label_str, 0)
        return video_tensor, label
