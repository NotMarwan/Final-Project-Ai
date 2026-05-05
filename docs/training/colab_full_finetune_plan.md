# Colab Full Fine-Tuning Plan for Violence Detection

## Current Verified State

- **Dataset**: `/content/drive/MyDrive/violence_data` (1976 videos)
- **Manifest**: `/content/drive/MyDrive/AI-Sentinel/manifests/violence_data_manifest.jsonl`
  - Total entries: 1976
  - Train entries: 1581
  - Val entries: 395
  - Labels: normal, violence
- **Smoke success**: True (return code 0)
- **Checkpoint**: `/content/drive/MyDrive/AI-Sentinel/checkpoints/smoke/smoke_20260505_193015/smoke_checkpoint.pt`
- **Production weights**: `backend/best_model.pt` (never overwritten)
- **Model**: ViolenceDetector with legacy_slowfast profile
- **Input shape**: (B, 3, 32, 224, 224)

---

## Training Tool Audit

### Available Scripts

1. **`backend/train_finetune.py`** - Full training script
   - Supports multiple dataset sources (zips or directories)
   - Uses ViolenceDetector model with SlowFast backbone
   - Stratified split with validation ratio
   - Comprehensive metrics (accuracy, precision, recall, specificity, F1, balanced accuracy)
   - Best checkpoint selection based on F1 + balanced accuracy
   - Safety: validates output_dir to prevent overwriting production weights
   - Configurable: epochs, batch size, learning rate, weight decay
   - Default: 6 epochs, batch size 2, lr=2e-4

2. **`backend/tools/train_rwf2000_smoke.py`** - Smoke test only
   - Safety capped at 8 train samples, 1 epoch
   - Only supports legacy_slowfast profile
   - Not suitable for full training

### Recommendation
Use `backend/train_finetune.py` for full fine-tuning. It has all necessary safety checks and comprehensive metrics.

---

## Runtime Plan

### GPU Check Cell (Required before training)

```python
import torch
import os

print("=== GPU/RUNTIME CHECK ===")
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    device = "cuda"
    gpu_name = torch.cuda.get_device_name(0)
    print(f"GPU: {gpu_name}")
    
    # Check available memory
    torch.cuda.empty_cache()
    total_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
    allocated = torch.cuda.memory_allocated(0) / 1e9
    reserved = torch.cuda.memory_reserved(0) / 1e9
    
    print(f"Total GPU memory: {total_memory:.2f} GB")
    print(f"Currently allocated: {allocated:.2f} GB")
    print(f"Currently reserved: {reserved:.2f} GB")
    print(f"Available: {total_memory - reserved:.2f} GB")
    
    # Recommend batch size based on memory
    if total_memory >= 16:
        recommended_bs = 4
    elif total_memory >= 8:
        recommended_bs = 2
    else:
        recommended_bs = 1
else:
    device = "cpu"
    gpu_name = "N/A (using CPU)"
    recommended_bs = 2  # CPU can handle larger batches
    print("WARNING: CUDA not available. Training will be slow on CPU.")

print(f"\nRecommended device: {device}")
print(f"Recommended batch size: {recommended_bs}")

# Set environment
os.environ["CUDA_VISIBLE_DEVICES"] = "0" if device == "cuda" else ""
```

### OOM Fallback Plan

If CUDA Out of Memory occurs:
1. Reduce batch size by half
2. If still OOM, switch to CPU (slow but works)
3. Consider reducing frame resolution (edit `FRAME_SIZE` in train_finetune.py)

---

## Proposed Training Stages

| Stage | Train Samples | Val Samples | Epochs | Goal | Approval Needed |
|-------|---------------|-------------|--------|------|---------------|
| 1 (Sanity) | 32 | 32 | 1 | Verify data loading and training loop | No (after smoke success) |
| 2 (Controlled) | 128 | 128 | 1 | Test full pipeline with small subset | Yes |
| 3 (Full) | 1581 | 395 | 3 | Full fine-tuning | Yes |

### Why Staged Approach?
- **Stage 1**: Quick sanity check (~2-5 minutes). Verifies data loading, model forward pass, checkpoint saving.
- **Stage 2**: Medium test (~10-20 minutes). Tests training stability with more data.
- **Stage 3**: Full training (~1-3 hours). Actual fine-tuning with full dataset.

---

## Proposed Hyperparameters

### Base Configuration
- **Model**: ViolenceDetector (legacy_slowfast profile)
- **Input**: (B, 3, 32, 224, 224) - SlowFast expects (slow, fast) where slow = video[::4]
- **Optimizer**: AdamW
- **Loss**: CrossEntropyLoss
- **Device**: cuda (if available) else cpu

### Stage-Specific Parameters

| Parameter | Stage 1 | Stage 2 | Stage 3 |
|-----------|---------|---------|---------|
| Batch size | 2 | 2 or 4 | 2 or 4 (based on GPU) |
| Learning rate | 1e-4 | 3e-5 | 1e-5 |
| Epochs | 1 | 1 | 3 |
| Weight decay | 1e-4 | 1e-4 | 1e-4 |
| Val ratio | 0.5 (for small test) | 0.5 | 0.2 |
| Unfreeze backbone | False | False | True (last 2 stages) |

### Why These Values?
- **Learning rate**: Starts higher for quick convergence, decreases for fine-tuning to preserve learned features.
- **Batch size**: Conservative to avoid OOM. Increase if GPU memory allows.
- **Epochs**: 3 is enough for fine-tuning without overfitting (dataset is small).
- **Weight decay**: Standard value for AdamW to prevent overfitting.
- **Unfreeze backbone**: Initially frozen to only train classification head. Unfreeze later for full fine-tuning.

---

## Evaluation Plan

### Metrics Tracked
- **Accuracy**: Overall correctness (can be misleading with imbalanced data)
- **Precision**: Of predicted violence, how many were correct? (minimize false positives)
- **Recall**: Of actual violence, how many were detected? (minimize false negatives)
- **Specificity**: Of actual normal, how many were correctly identified?
- **F1 Score**: Harmonic mean of precision and recall (balanced metric)
- **Balanced Accuracy**: Mean of recall and specificity (handles imbalance)
- **Train/Val Loss**: Monitor overfitting

### Why Accuracy Alone Is Not Enough
With 1581 train / 395 val, if 80% are "violence":
- Predicting all as "violence" gives 80% accuracy but 0% precision for "normal"
- Need per-class metrics and confusion matrix

### Confusion Matrix Analysis
```
                    Predicted
                 Normal  Violence
Actual Normal    [  TN  ] [  FP  ]  (FP = false alarms)
       Violence  [  FN  ] [  TP  ]
```

- **False Positives (FP)**: Normal videos misclassified as violence (waste resources)
- **False Negatives (FN)**: Violence missed (security risk)

### Success Criteria
- Val F1 > 0.85
- Val Balanced Accuracy > 0.85
- No more than 5% gap between train and val metrics (no overfitting)
- False positive rate < 10%
- False negative rate < 10%

---

## Safety Plan

### Checkpoint Output Path
```
/content/drive/MyDrive/AI-Sentinel/checkpoints/full_finetune/<run_id>/
```

Where `<run_id>` = `run_YYYYMMDD_HHMMSS`

### Output Files
1. **`best_candidate.pt`** - Best model based on F1 + balanced accuracy
   - Contains: model_state_dict, optimizer_state_dict, metrics, history, trainArgs
   - Source weights path included
   - Git commit hash included (if available)
   
2. **`last_checkpoint.pt`** - Last epoch checkpoint (for resuming)

3. **`training_summary.json`** - Final metrics and config
   ```json
   {
     "run_id": "run_20260505_193015",
     "timestamp": "2026-05-05T19:30:15",
     "git_commit": "d25868b",
     "manifest_path": "/content/drive/MyDrive/AI-Sentinel/manifests/violence_data_manifest.jsonl",
     "source_weights": "/content/ai-sentinel/backend/best_model.pt",
     "train_samples": 1581,
     "val_samples": 395,
     "epochs_completed": 3,
     "best_val_f1": 0.92,
     "best_val_balanced_accuracy": 0.91,
     "best_val_loss": 0.15,
     "final_train_loss": 0.08,
     "training_time_sec": 3600
   }
   ```

4. **`metrics_history.jsonl`** - Per-epoch metrics
   ```
   {"epoch": 1, "trainLoss": 0.45, "valLoss": 0.30, "valF1": 0.85, ...}
   {"epoch": 2, "trainLoss": 0.25, "valLoss": 0.18, "valF1": 0.90, ...}
   ```

5. **`confusion_matrix.json`** - Final confusion matrix
   ```json
   {
     "tn": 180, "fp": 20, "fn": 15, "tp": 180,
     "precision": 0.90, "recall": 0.92, "specificity": 0.90
   }
   ```

6. **`eval_summary.json`** - Detailed per-class metrics

### `backend/best_model.pt` Overwrite Prevention
- `train_finetune.py` outputs to `backend/best_model_finetuned.pt` by default
- Checkpoint safety validation in `TrainConfig` prevents output to `backend/best_model.pt`
- All checkpoints go under `/content/drive/MyDrive/AI-Sentinel/checkpoints/full_finetune/`

### Rollback Plan
1. **If training fails**: Delete the run directory, no harm done.
2. **If metrics are worse**: Keep `backend/best_model.pt` unchanged.
3. **If metrics improve**: 
   - Copy `best_candidate.pt` to local `backend/best_model_finetuned.pt`
   - Test locally before promoting
   - Promotion requires user approval

### Promotion Process (Local Re-import)
```bash
# After Colab training, download best checkpoint
# Then locally:
cd "C:\Users\PCD\Downloads\Final Project AI Sentinel"

# Backup current production model
cp backend/best_model.pt backend/best_model.pt.backup

# Test the fine-tuned model
python -c "
from backend.inference import ViolenceDetector
import torch
model = ViolenceDetector(num_classes=2)
checkpoint = torch.load('backend/best_model_finetuned.pt', map_location='cpu')
model.load_state_dict(checkpoint['model_state_dict'])
print('Fine-tuned model loaded successfully')
print('Metrics:', checkpoint.get('metrics', {}))
"

# If satisfied, promote (requires user approval)
# cp backend/best_model_finetuned.pt backend/best_model.pt
```

---

## Notebook / Docs

### New Notebook Created
- **Path**: `notebooks/colab_full_finetune.ipynb`
- **Purpose**: Full fine-tuning (separate from probe notebook)
- **Training disabled by default**: `RUN_FULL_TRAINING = False`

### Cells Structure
1. Mount Google Drive
2. Check for dataset and manifest
3. Extract code zip
4. Install dependencies
5. Verify project setup
6. GPU/Runtime check
7. Training configuration preview
8. **[GUARDED]** Full fine-tuning cell
9. Parse results
10. Save report

### Safety Guard
```python
RUN_FULL_TRAINING = False  # Set to True only after user approval

if not RUN_FULL_TRAINING:
    raise RuntimeError(
        "Full training is disabled. "
        "Set RUN_FULL_TRAINING=True only after user approval."
    )
```

---

## Exact Commands for Training (After Approval)

### Stage 1: Sanity Check (32/32, 1 epoch)
```python
import os, subprocess, time
from pathlib import Path

os.chdir("/content/ai-sentinel")

env = os.environ.copy()
env["PYTHONPATH"] = "backend"

cmd = [
    "python", "backend/train_finetune.py",
    "--sources", "/content/drive/MyDrive/violence_data",
    "--weights", "backend/best_model.pt",
    "--output", "/content/drive/MyDrive/AI-Sentinel/checkpoints/full_finetune/stage1_sanity/best_candidate.pt",
    "--epochs", "1",
    "--batch-size", "2",
    "--lr", "1e-4",
    "--val-ratio", "0.5",
    "--max-samples", "64",  # 32 train + 32 val
    "--num-workers", "2",
    "--seed", "42",
]

print(f"Running: {' '.join(cmd)}")
start = time.time()
result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
print(f"Completed in {time.time()-start:.2f}s")
print(f"Return code: {result.returncode}")
print(f"STDOUT:\n{result.stdout[-4000:]}")
print(f"STDERR:\n{result.stderr[-4000:]}")
```

### Stage 2 & 3: Similar commands with adjusted parameters

---

## Verdict

- **Start full fine-tuning now**: No (waiting for user approval)
- **Need user approval**: Yes
- **Recommended next step**: 
  1. Review this plan
  2. Approve Stage 1 sanity check
  3. Review Stage 1 results
  4. Approve Stage 2 and/or Stage 3

---

*Plan created: 2026-05-05*
*Based on: Successful smoke verification (commit d25868b)*
