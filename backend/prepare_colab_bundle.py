from __future__ import annotations

import json
import secrets
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
DIST_DIR = ROOT_DIR / ".runlogs" / "colab_bridge"
CODE_ZIP = DIST_DIR / "colab_bundle.zip"
MANIFEST_PATH = DIST_DIR / "manifest.json"
DEFAULT_DATASET = ROOT_DIR / "val-20260418T185437Z-3-001.zip"


FILES_TO_BUNDLE = [
    ROOT_DIR / "backend" / "api.py",
    ROOT_DIR / "backend" / "inference.py",
    ROOT_DIR / "backend" / "fusion.py",
    ROOT_DIR / "backend" / "weapon.py",
    ROOT_DIR / "backend" / "calibration_utils.py",
    ROOT_DIR / "backend" / "train_finetune.py",
    ROOT_DIR / "backend" / "train_calibration.py",
    ROOT_DIR / "backend" / "requirements-train.txt",
    ROOT_DIR / "backend" / ".env.example",
    ROOT_DIR / "backend" / "config.yml",
    ROOT_DIR / "docs" / "colab-training.md",
]


def build_bundle() -> dict:
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(CODE_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in FILES_TO_BUNDLE:
            if path.exists():
                archive.write(path, path.relative_to(ROOT_DIR).as_posix())

    token = secrets.token_urlsafe(24)
    dataset_path = DEFAULT_DATASET.resolve()
    weights_path = (BACKEND_DIR / "best_model.pt").resolve()
    manifest = {
        "token": token,
        "bundle": {
            "filename": CODE_ZIP.name,
            "path": str(CODE_ZIP.resolve()),
        },
        "dataset": {
            "filename": dataset_path.name,
            "path": str(dataset_path),
        },
        "weights": {
            "filename": weights_path.name,
            "path": str(weights_path),
        },
        "uploads": {
            "best_model.pt": str((BACKEND_DIR / "best_model.pt").resolve()),
            "model_calibration.json": str((BACKEND_DIR / "model_calibration.json").resolve()),
            "training_report.json": str((BACKEND_DIR / "training_report.json").resolve()),
        },
    }

    with open(MANIFEST_PATH, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    return manifest


if __name__ == "__main__":
    payload = build_bundle()
    print(json.dumps(payload, indent=2))
