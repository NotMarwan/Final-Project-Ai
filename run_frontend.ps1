# AI-Sentinel — Start Frontend
# Run in a dedicated PowerShell window (backend must already be running).
# Usage: .\run_frontend.ps1

Write-Host "=== AI-Sentinel Frontend ===" -ForegroundColor Cyan

# Check node_modules
if (-not (Test-Path "node_modules")) {
    Write-Host "ERROR: node_modules not found. Run .\setup_windows.ps1 first." -ForegroundColor Red
    exit 1
}

# Check .env.local
if (-not (Test-Path ".env.local")) {
    Write-Host "WARNING: .env.local not found. Copy from .env.local.example." -ForegroundColor Yellow
}

Write-Host "Starting frontend on http://localhost:3000 ..." -ForegroundColor Green
Write-Host "Make sure the backend is already running on http://localhost:8002" -ForegroundColor Yellow
Write-Host ""

npm run dev
