# AI-Sentinel — Start Backend
# Run in a dedicated PowerShell window.
# Usage: .\run_backend.ps1

Write-Host "=== AI-Sentinel Backend ===" -ForegroundColor Cyan

# Check virtual environment
if (-not (Test-Path "venv\Scripts\activate.ps1")) {
    Write-Host "ERROR: Virtual environment not found. Run .\setup_windows.ps1 first." -ForegroundColor Red
    exit 1
}

# Check model weights
if (-not (Test-Path "backend\best_model.pt")) {
    Write-Host "WARNING: best_model.pt not found. Run 'git lfs pull' first." -ForegroundColor Yellow
    Write-Host "         Backend will start in demo mode without live violence detection." -ForegroundColor Yellow
}

# Check .env
if (-not (Test-Path "backend\.env")) {
    Write-Host "WARNING: backend\.env not found. Copy from backend\.env.example and fill in keys." -ForegroundColor Yellow
}

Write-Host "Starting backend on http://localhost:8002 ..." -ForegroundColor Green

# Activate venv and start backend
& "venv\Scripts\python.exe" -m uvicorn api:app --host 0.0.0.0 --port 8002 --app-dir backend
