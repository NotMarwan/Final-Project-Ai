# Colab Training

This project now includes two training paths:

- `backend/train_finetune.py`: real GPU fine-tuning for the existing `SlowFast` checkpoint.
- `backend/train_calibration.py`: fast calibration training for confidence, threshold, and class index.

## Recommended Colab flow

Mount Drive and clone/upload the project, then run:

```bash
cd "/content/Final Project AI Sentinel"
pip install -r backend/requirements-train.txt
python -m backend.train_finetune \
  --sources "/content/Final Project AI Sentinel/val-20260418T185437Z-3-001.zip" \
  --weights "/content/Final Project AI Sentinel/backend/best_model.pt" \
  --output "/content/Final Project AI Sentinel/backend/best_model.pt" \
  --epochs 6 \
  --batch-size 2 \
  --include-test-positives
python -m backend.train_calibration \
  --dataset-zip "/content/Final Project AI Sentinel/val-20260418T185437Z-3-001.zip" \
  --weights "/content/Final Project AI Sentinel/backend/best_model.pt" \
  --output "/content/Final Project AI Sentinel/backend/model_calibration.json"
```

## Notes

- Start with `head-only` fine-tuning first. The script freezes the backbone by default.
- Add `--unfreeze-backbone` only after the head-only pass is stable.
- The runtime backend automatically reads `backend/model_calibration.json` when it exists.
- If you add more datasets later, pass multiple sources to `--sources`.
