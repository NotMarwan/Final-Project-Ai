# Colab Zero-Touch Plan

## Goal

Train on Colab GPU without downloading new heavy datasets to the local machine, and return the trained artifacts directly to this project.

## Architecture

1. Local bridge builds a small code bundle and exposes:
   - current training code
   - `backend/best_model.pt`
   - `val-20260418T185437Z-3-001.zip`
2. Colab notebook pulls those files over a temporary public tunnel.
3. Colab runs:
   - `backend.train_finetune`
   - `backend.train_calibration`
4. Colab uploads back:
   - `best_model.pt`
   - `model_calibration.json`
   - `training_report.json`

## Why this path

- No new dataset is downloaded to the local PC.
- The heavy training compute happens on Colab GPU.
- The trained outputs come back into the project automatically.
- We stay compatible with the current `SlowFast` checkpoint and runtime.

## Limits

- Opening Colab and running the notebook still requires Google account access, which cannot be executed from the local terminal alone.
- The local machine must stay online while the notebook is training because it is serving the dataset and receiving the outputs.

## Files

- `backend/prepare_colab_bundle.py`
- `backend/colab_bridge_server.py`
- `backend/render_colab_notebook.py`
- `notebooks/colab_zero_touch_train.ipynb`
- `notebooks/colab_zero_touch_train.ready.ipynb`
- `start-colab-bridge.ps1`

## Operator Flow

1. Run `start-colab-bridge.ps1`.
2. Read `.runlogs/colab_bridge/colab-launch.txt`.
3. Open the ready notebook at `notebooks/colab_zero_touch_train.ready.ipynb`.
4. In Colab, use `Runtime -> Run all`.
5. Keep the local machine online until training finishes and uploads:
   - `backend/best_model.pt`
   - `backend/model_calibration.json`
   - `backend/training_report.json`
