import yaml
import torch
from torch.utils.data import Dataset, DataLoader
from pathlib import Path
import numpy as np
import cv2

class VideoClipDataset(Dataset):
    def __init__(self, frames, clip_length=32, stride=16, label=0, transform=None):
        self.frames = frames
        self.clip_length = clip_length
        self.stride = stride
        self.label = label
        self.transform = transform
        
        self.clips = []
        for i in range(0, len(frames) - clip_length + 1, stride):
            self.clips.append(frames[i:i+clip_length])

    def __len__(self):
        return len(self.clips)

    def __getitem__(self, idx):
        clip = self.clips[idx]
        
        # Preprocess frames
        processed = []
        for frame in clip:
            if self.transform:
                frame = self.transform(frame)
            else:
                # Basic normalization
                frame = frame.astype(np.float32) / 255.0
                frame = (frame - 0.45) / 0.225
            processed.append(frame)
        
        # Stack to (C, T, H, W)
        tensor = np.stack(processed, axis=0).transpose(3, 0, 1, 2)
        return torch.from_numpy(tensor), self.label

class RWCDataset(Dataset):
    def __init__(self, root_path, split="train", transform=None):
        self.root_path = Path(root_path)
        self.split = split
        self.transform = transform
        # Mock data for testing if path doesn't exist
        self.data = [] if not self.root_path.exists() else list(self.root_path.glob("*.mp4"))

    def __len__(self):
        return len(self.data) or 10 # Return dummy size for testing

    def __getitem__(self, idx):
        # Mock item for testing
        dummy_frames = [np.random.randint(0, 255, (160, 160, 3), dtype=np.uint8) for _ in range(32)]
        clip_dataset = VideoClipDataset(dummy_frames, label=1, transform=self.transform)
        return clip_dataset[0]

class UFCDataset(Dataset):
    def __init__(self, root_path, split="train", transform=None):
        self.root_path = Path(root_path)
        self.split = split
        self.transform = transform
        self.data = [] if not self.root_path.exists() else list(self.root_path.glob("*.mp4"))

    def __len__(self):
        return len(self.data) or 10

    def __getitem__(self, idx):
        dummy_frames = [np.random.randint(0, 255, (160, 160, 3), dtype=np.uint8) for _ in range(32)]
        clip_dataset = VideoClipDataset(dummy_frames, label=1, transform=self.transform)
        return clip_dataset[0]

class MultiDatasetLoader:
    def __init__(self, config):
        self.config = config
        self.datasets = config.get("datasets", {})

    @classmethod
    def from_config(cls, config_path):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        return cls(config)
