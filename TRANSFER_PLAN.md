# AI-Sentinel — Transfer Plan

**Branch:** `final-demo-transfer`  
**Purpose:** Clean transfer to a new laptop for the final graduation project demo.  
**Date:** 2026-05-20

---

## What Is Tracked in Regular Git

All text-based source files that make up the project code and configuration:

| Category | Files / Folders |
|----------|----------------|
| Backend Python code | `backend/*.py`, `backend/tests/`, `backend/training/` |
| Frontend TypeScript/React | `app/`, `components/`, `hooks/`, `lib/`, `public/` |
| Configuration | `backend/config.yml`, `next.config.mjs`, `package.json`, `Dockerfile`, `docker-compose.yml` |
| Environment templates | `backend/.env.example`, `.env.local.example` |
| Thesis figures & docs | `thesis_phase2/figures/*.png`, `thesis_phase2/figures/*.jpg` |
| Presentation brief | `CLAUDE_DESIGN_PRESENTATION_BRIEF.md`, `CLAUDE_DESIGN_PROMPT.txt` |
| Setup guides | `SETUP_NEW_LAPTOP.md`, `TRANSFER_PLAN.md`, `EVIDENCE_NOT_INCLUDED.md` |
| Setup scripts | `setup_windows.ps1`, `run_backend.ps1`, `run_frontend.ps1` |
| CI workflow | `.github/workflows/` |

---

## What Is Tracked in Git LFS

Large binary files required to run the system, stored via Git Large File Storage:

| File | Size | Purpose |
|------|------|---------|
| `backend/best_model.pt` | ~142 MB | Violence detection model (X3D-M) — required |
| `backend/weapon_hadi_yolo.pt` | ~6 MB | Weapon detection model (YOLOv8) — required |
| `backend/models/weapon_yolo.onnx` | ~99 MB | ONNX weapon model — optional fallback |
| `backend/models/person_yolo.onnx` | ~12 MB | Person detection model |
| `demo_assets/videos/Wq0BuA8GM84_0.avi` | ~4.5 MB | Demo clip EXAMPLE-01 (Fight Sample 1) |
| `demo_assets/videos/YDOJvzChqSg_0 (1).avi` | ~3.3 MB | Demo clip EXAMPLE-02 (Fight Sample 2) |
| `demo_assets/videos/FXC43fACfPc_0.avi` | ~24 MB | Demo clip EXAMPLE-03 (Violence Sample 3) |
| `thesis_phase2/main.pdf` | — | Compiled thesis PDF |
| `thesis_phase2/GP Documentation DLRPVD.pdf` | — | Supporting documentation |

**Note:** After cloning, run `git lfs pull` to download all LFS files.

---

## What Is Ignored

| Category | Why Ignored |
|----------|-------------|
| `backend/evidence_clips/` | 320 generated MP4 files, 4.1 GB total — regenerated at demo runtime |
| `backend/thumbnails/` | Generated at runtime |
| `venv/` / `backend/venv/` | Virtual environment — recreated with `pip install -r requirements.txt` |
| `node_modules/` | NPM packages — recreated with `npm install` |
| `.next/` | Next.js build cache — recreated with `npm run dev` |
| `.runlogs/` | Training checkpoints and experiment logs (multi-GB) |
| `.data/` | Raw training datasets (multi-GB) |
| `unrelated/` | Local development backups, installers, test copies — not needed |
| `test/` | Original demo clips folder (replaced by `demo_assets/videos/`) |
| `backend/.env` | Contains real secrets — never committed |
| `.env.local` | Contains real frontend config — never committed |
| `backend/best_model.pt.local_mismatch_backup` | Duplicate backup, not needed |
| `backend/weapon_cs2_yolo12.pt` | Alternative model not used in demo config |
| `backend/weapon_yolo.pt` | Alternative model not used in demo config |
| `desktop/dist/` | Electron build output |
| `android/app/build/` | Android build output |

---

## Required for Demo — Checklist

After cloning on a new laptop, verify these exist:

- [ ] `backend/best_model.pt` (download via `git lfs pull`)
- [ ] `backend/weapon_hadi_yolo.pt` (download via `git lfs pull`)
- [ ] `demo_assets/videos/Wq0BuA8GM84_0.avi`
- [ ] `demo_assets/videos/YDOJvzChqSg_0 (1).avi`
- [ ] `demo_assets/videos/FXC43fACfPc_0.avi`
- [ ] `backend/.env` (copy from `backend/.env.example`, fill real keys)
- [ ] Python virtual environment created and activated
- [ ] `npm install` completed

---

## Optional Files

These are included for reference but not required to run the demo:

- `thesis_phase2/` — Thesis LaTeX source and compiled PDF
- `CLAUDE_DESIGN_PRESENTATION_BRIEF.md` — Presentation design brief
- `GRADUATION_EVALUATION_REPORT.md` — Internal evaluation report
- `backend/models/weapon_yolo.onnx` — ONNX export (LFS, only needed if running ONNX inference mode)

---

## Files That Must Never Be Pushed

| File | Reason |
|------|--------|
| `backend/.env` | Contains Telegram bot token, Groq API key, OpenRouter key |
| `.env.local` | Contains frontend API keys |
| `backend/config.yml` | May contain Telegram chat ID — review before push |
| Any `*.env*` file (except `.example`) | Secrets |
