# Local Only Files

## Must Stay Local

- `backend/best_model.pt`
- `.runlogs/**/best_model.pt`
- `.runlogs/**/*.pt`
- `dummy/**/*.pt`
- `.data/`
- `temp_rwf/`
- `test/*.avi`
- `backend/evidence_clips/`
- `backend/thumbnails/`
- `backend/reports/` generated runtime PDFs and artifacts
- `val-20260418T185437Z-3-001.zip`
- `ai-sentinel-colab-code.zip`
- `live_alert_runtime_patch.zip`
- `components/files.zip`
- `components/files (1).zip`
- `backend/cloudflared-windows-amd64.exe`
- `*.db`
- `.env*` except safe examples

## Why Local Only

- too large for normal GitHub history
- may contain private datasets, generated evidence, or demo media
- may be runtime-only or environment-specific
- model/checkpoint artifacts must not be pushed without explicit Git LFS approval

## Model SHA Notes

- Stable runtime reference SHA256:
  `2c8222d3663a0ac54ed9e1c5b372378b771a8dd0f3c0ed1ed04cee4013620d01`
- Current workspace-local `backend/best_model.pt` SHA256:
  `1fb38eeb54821d827a4621ac3fce4ad98488bc05fbf99df9ab78a13ed223b6cb`
