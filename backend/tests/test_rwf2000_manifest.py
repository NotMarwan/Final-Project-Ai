import unittest
import json
import os
import tempfile
from pathlib import Path
from tools.build_rwf2000_manifest import build_manifest

class TestRWF2000Manifest(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.dataset_root = Path(self.test_dir.name)
        
        # Create mock structure
        # train/fight (3), train/nonfight (3)
        # val/fight (1), val/nonfight (1)
        # Total 8. Default splits: 6 train, 2 val.
        
        for split in ["train", "val"]:
            for label in ["fight", "nonfight"]:
                path = self.dataset_root / split / label
                path.mkdir(parents=True, exist_ok=True)
                count = 3 if split == "train" else 1
                for i in range(count):
                    (path / f"video_{i}.avi").write_text("dummy")
        
        self.output_file = Path(self.test_dir.name) / "manifest.jsonl"

    def tearDown(self):
        self.test_dir.cleanup()

    def test_default_build(self):
        build_manifest(str(self.dataset_root), str(self.output_file))
        
        with open(self.output_file, "r") as f:
            lines = f.readlines()
        
        self.assertEqual(len(lines), 8)
        entries = [json.loads(l) for l in lines]
        
        train_count = sum(1 for e in entries if e["split"] == "train")
        val_count = sum(1 for e in entries if e["split"] == "val")
        
        self.assertEqual(train_count, 6)
        self.assertEqual(val_count, 2)
        
        # Check mapping
        for e in entries:
            # Be specific to avoid "fight" in "nonfight"
            if e["original_label"].lower() == "fight":
                self.assertEqual(e["label"], "violence")
            elif e["original_label"].lower() == "nonfight":
                self.assertEqual(e["label"], "normal")

    def test_ratio_split(self):
        # 50/50 split on 8 samples should give 4/4
        build_manifest(str(self.dataset_root), str(self.output_file), val_ratio=0.5, seed=42)
        
        with open(self.output_file, "r") as f:
            lines = f.readlines()
        
        entries = [json.loads(l) for l in lines]
        
        train_count = sum(1 for e in entries if e["split"] == "train")
        val_count = sum(1 for e in entries if e["split"] == "val")
        
        self.assertEqual(train_count, 4)
        self.assertEqual(val_count, 4)
        
        # Original split preserved
        for e in entries:
            self.assertIn("original_split", e)
            
    def test_determinism(self):
        build_manifest(str(self.dataset_root), str(self.output_file), val_ratio=0.5, seed=123)
        with open(self.output_file, "r") as f:
            content1 = f.read()
            
        build_manifest(str(self.dataset_root), str(self.output_file), val_ratio=0.5, seed=123)
        with open(self.output_file, "r") as f:
            content2 = f.read()
            
        self.assertEqual(content1, content2)
        
        # Different seed should likely differ
        build_manifest(str(self.dataset_root), str(self.output_file), val_ratio=0.5, seed=456)
        with open(self.output_file, "r") as f:
            content3 = f.read()
            
        self.assertNotEqual(content1, content3)

if __name__ == "__main__":
    unittest.main()
