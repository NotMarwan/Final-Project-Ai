import json
from argparse import Namespace
from collections import Counter


def _write_manifest(path, *, train_per_label=20, val_per_label=20):
    rows = []
    for split, per_label in (("train", train_per_label), ("val", val_per_label)):
        for index in range(per_label):
            rows.append(
                {
                    "video_path": f"{split}_normal_{index}.avi",
                    "label": "normal",
                    "split": split,
                }
            )
        for index in range(per_label):
            rows.append(
                {
                    "video_path": f"{split}_violence_{index}.avi",
                    "label": "violence",
                    "split": split,
                }
            )
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_build_datasets_balances_capped_manifest_sampling(tmp_path):
    from train_finetune import build_datasets

    manifest_path = tmp_path / "ordered_manifest.jsonl"
    _write_manifest(manifest_path)
    args = Namespace(
        manifest=str(manifest_path),
        sources=None,
        max_train_samples=32,
        max_val_samples=32,
        include_test_positives=False,
        val_ratio=0.15,
        seed=42,
    )

    train_dataset, val_dataset, summary = build_datasets(args, cache_dir=tmp_path / "cache")
    train_labels = Counter(train_dataset.labels)
    val_labels = Counter(val_dataset.labels)

    assert train_labels == Counter({0: 16, 1: 16})
    assert val_labels == Counter({0: 16, 1: 16})
    assert summary["train_label_counts"] == {0: 16, 1: 16}
    assert summary["val_label_counts"] == {0: 16, 1: 16}


def test_build_datasets_manifest_sampling_is_deterministic(tmp_path):
    from train_finetune import build_datasets

    manifest_path = tmp_path / "ordered_manifest.jsonl"
    _write_manifest(manifest_path)
    args = Namespace(
        manifest=str(manifest_path),
        sources=None,
        max_train_samples=32,
        max_val_samples=32,
        include_test_positives=False,
        val_ratio=0.15,
        seed=42,
    )

    first_train, first_val, _ = build_datasets(args, cache_dir=tmp_path / "cache")
    second_train, second_val, _ = build_datasets(args, cache_dir=tmp_path / "cache")

    assert first_train.dataset.samples == second_train.dataset.samples
    assert first_val.dataset.samples == second_val.dataset.samples
