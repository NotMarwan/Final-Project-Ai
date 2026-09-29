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

    def test_non_violence_label_mapping(self):
        """Test that non-violence labels map to normal, and violence to violence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_root = Path(tmpdir)
            # Create structure with non-violence label
            for split in ["train", "val"]:
                (dataset_root / split / "violence").mkdir(parents=True, exist_ok=True)
                (dataset_root / split / "non-violence").mkdir(parents=True, exist_ok=True)
            # Add video files
            (dataset_root / "train" / "violence" / "a.avi").write_text("dummy")
            (dataset_root / "train" / "non-violence" / "b.avi").write_text("dummy")
            (dataset_root / "val" / "violence" / "c.avi").write_text("dummy")
            (dataset_root / "val" / "non-violence" / "d.avi").write_text("dummy")
            
            output_file = Path(tmpdir) / "manifest.jsonl"
            build_manifest(str(dataset_root), str(output_file))
            
            with open(output_file, "r") as f:
                entries = [json.loads(line) for line in f]
            
            # Total entries: 4
            self.assertEqual(len(entries), 4)
            
            # Check label mappings
            label_map = {e["original_label"]: e["label"] for e in entries}
            self.assertEqual(label_map["violence"], "violence")
            self.assertEqual(label_map["non-violence"], "normal")
            
            # Check splits
            train_entries = [e for e in entries if e["split"] == "train"]
            val_entries = [e for e in entries if e["split"] == "val"]
            self.assertEqual(len(train_entries), 2)
            self.assertEqual(len(val_entries), 2)
            
            # Check both labels exist in each split
            for split_entries in [train_entries, val_entries]:
                labels = {e["label"] for e in split_entries}
                self.assertIn("violence", labels)
                self.assertIn("normal", labels)
            
            # Check original_split is present
            for e in entries:
                self.assertIn("original_split", e)
                self.assertEqual(e["original_split"], e["split"])
            
            # Check no file moves (files still exist)
            self.assertTrue((dataset_root / "train" / "violence" / "a.avi").exists())
            self.assertTrue((dataset_root / "train" / "non-violence" / "b.avi").exists())

    def test_variant_normal_labels(self):
        """Test non_violence, nonviolence, non-fight map to normal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_root = Path(tmpdir)
            # Create variant labels
            variants = [
                ("train", "non_violence", "x.avi"),
                ("train", "nonviolence", "y.avi"),
                ("train", "non-fight", "z.avi"),
                ("val", "non_violence", "u.avi"),
                ("val", "nonviolence", "v.avi"),
                ("val", "non-fight", "w.avi"),
            ]
            for split, label, fname in variants:
                (dataset_root / split / label).mkdir(parents=True, exist_ok=True)
                (dataset_root / split / label / fname).write_text("dummy")
            # Also add violence labels to check mapping
            (dataset_root / "train" / "violence").mkdir(parents=True, exist_ok=True)
            (dataset_root / "val" / "violence").mkdir(parents=True, exist_ok=True)
            (dataset_root / "train" / "violence" / "a.avi").write_text("dummy")
            (dataset_root / "val" / "violence" / "b.avi").write_text("dummy")
            
            output_file = Path(tmpdir) / "manifest.jsonl"
            build_manifest(str(dataset_root), str(output_file))
            
            with open(output_file, "r") as f:
                entries = [json.loads(line) for line in f]
            
            # Total entries: 6 variants + 2 violence = 8
            self.assertEqual(len(entries), 8)
            
            # Check all variant labels map to normal
            variant_labels = {"non_violence", "nonviolence", "non-fight"}
            for e in entries:
                if e["original_label"] in variant_labels:
                    self.assertEqual(e["label"], "normal")
                elif e["original_label"] == "violence":
                    self.assertEqual(e["label"], "violence")
            
            # Check all labels are either normal or violence
            all_labels = {e["label"] for e in entries}
            self.assertEqual(all_labels, {"normal", "violence"})

if __name__ == "__main__":
    unittest.main()
