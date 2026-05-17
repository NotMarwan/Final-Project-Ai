# Crash-Resilient GPU Activation Plan

## Root Cause Analysis

**Problem:** System crashes during long-running commands
- Total RAM: 16GB
- Available RAM: ~4GB (opencode uses 3.7GB)
- Long commands (pytest, pip) exhaust memory → Windows kills process

**Solution:** Break work into small, fast commands (<30s each) with state saved between steps.

## Execution Rules

1. **No command runs longer than 30 seconds**
2. **Save state to file after each step**
3. **Use `--timeout 30000` for all bash commands**
4. **If crash occurs, read state file and resume**

## State File

Location: `C:\Users\PCD\Downloads\Final Project AI Sentinel\.gpu-progress.json`

```json
{
  "lastCompletedStep": "N",
  "timestamp": "ISO date",
  "status": "in_progress|completed|failed"
}
```

## Steps (Each <30 seconds)

### Phase 1: Verify Current State (Steps 1-3)
- Step 1: Check venv exists
- Step 2: Check PyTorch CUDA installed
- Step 3: Check GPU detected

### Phase 2: Install Missing Dependencies (Steps 4-6)
- Step 4: Install pytest (if missing)
- Step 5: Install numpy<2 (if needed)
- Step 6: Install other requirements

### Phase 3: Create Test Files (Steps 7-8)
- Step 7: Write test_gpu_activation.py
- Step 8: Write scripts/verify_gpu.py

### Phase 4: Run Tests (Steps 9-11)
- Step 9: Run single test file (quick)
- Step 10: Run verify script
- Step 11: Run device tests

### Phase 5: Documentation (Steps 12-13)
- Step 12: Write GPU_SETUP.md
- Step 13: Commit all changes

## Resume Instructions

After any crash:
1. Read `.gpu-progress.json`
2. Find `lastCompletedStep`
3. Execute next step number
4. Update state file
