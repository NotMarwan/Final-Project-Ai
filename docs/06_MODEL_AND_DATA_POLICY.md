# Model And Data Policy

## Model Weights

- Do not commit model weights directly to normal GitHub history.
- Do not commit `*.pt`, `*.pth`, or `*.ckpt` unless Git LFS is explicitly approved and configured.
- Always document the canonical model SHA256.
- Keep the canonical model file in Drive or a preserved local-only backup location.

## Datasets And Videos

- Do not commit datasets, raw videos, evidence clips, or checkpoints to normal GitHub history.
- Keep those assets as local-only or Drive-only preservation artifacts.
- Use manifests to record their paths, sizes, and notes.

## Local-Only Source Of Truth

- Large artifacts should be preserved locally and/or in Drive.
- `manifests/LOCAL_ONLY_FILES.md` is the quick reference.
- `manifests/FILE_MANIFEST_SHA256.csv` is the detailed per-file ledger for included preservation artifacts.

## Backup Policy

- Keep at least one local ZIP backup.
- Keep at least one GitHub-ready ZIP backup.
- Do not overwrite the only known-good model copy.

## Git LFS

Git LFS is not enabled automatically in this freeze. The current recommendation-only patterns are:

- `*.pt`
- `*.pth`
- `*.ckpt`
- `*.mp4`
- `*.zip`
