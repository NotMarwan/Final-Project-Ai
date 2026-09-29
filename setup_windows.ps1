# AI-Sentinel — Windows Setup Script
# Run this once after cloning to set up the environment.
# Usage: .\setup_windows.ps1

Write-Host "=== AI-Sentinel Setup ===" -ForegroundColor Cyan

# Step 1: Pull LFS files
Write-Host "`n[1/4] Pulling Git LFS files (model weights + demo videos)..." -ForegroundColor Yellow
git lfs pull
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: git lfs pull failed. Run it manually after setup." -ForegroundColor Red
}

# Step 2: Create Python virtual environment
Write-Host "`n[2/4] Creating Python virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path "venv")) {
    python -m venv venv
    Write-Host "Virtual environment created at ./venv" -ForegroundColor Green
} else {
    Write-Host "Virtual environment already exists." -ForegroundColor Green
}

# Step 3: Install backend requirements
Write-Host "`n[3/4] Installing backend Python dependencies..." -ForegroundColor Yellow
& "venv\Scripts\pip.exe" install -r backend\requirements.txt
if ($LASTEXITCODE -eq 0) {
    Write-Host "Backend dependencies installed." -ForegroundColor Green
} else {
    Write-Host "ERROR: pip install failed. Check requirements.txt and Python version." -ForegroundColor Red
}

# Step 4: Install frontend packages
Write-Host "`n[4/4] Installing frontend Node.js packages..." -ForegroundColor Yellow
npm install
if ($LASTEXITCODE -eq 0) {
    Write-Host "Frontend packages installed." -ForegroundColor Green
} else {
    Write-Host "ERROR: npm install failed. Check Node.js version (18+ required)." -ForegroundColor Red
}

# Step 5: Create .env files from examples if missing
Write-Host "`n[+] Checking environment files..." -ForegroundColor Yellow
if (-not (Test-Path "backend\.env")) {
    if (Test-Path "backend\.env.example") {
        Copy-Item "backend\.env.example" "backend\.env"
        Write-Host "Created backend/.env from example. Fill in your API keys." -ForegroundColor Yellow
    }
}
if (-not (Test-Path ".env.local")) {
    if (Test-Path ".env.local.example") {
        Copy-Item ".env.local.example" ".env.local"
        Write-Host "Created .env.local from example." -ForegroundColor Yellow
    }
}

# Final check
Write-Host "`n=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Edit backend\.env and fill in TELEGRAM_BOT_TOKEN, GROQ_API_KEY, etc."
Write-Host "  2. Run: .\run_backend.ps1   (in one PowerShell window)"
Write-Host "  3. Run: .\run_frontend.ps1  (in another PowerShell window)"
Write-Host "  4. Open: http://localhost:3000"

# Verify model weights exist
Write-Host "`n=== Model Weight Check ===" -ForegroundColor Cyan
if (Test-Path "backend\best_model.pt") {
    $sz = [math]::Round((Get-Item "backend\best_model.pt").Length / 1MB, 1)
    Write-Host "  best_model.pt        $sz MB   OK" -ForegroundColor Green
} else {
    Write-Host "  best_model.pt        MISSING — run: git lfs pull" -ForegroundColor Red
}
if (Test-Path "backend\weapon_hadi_yolo.pt") {
    $sz = [math]::Round((Get-Item "backend\weapon_hadi_yolo.pt").Length / 1MB, 1)
    Write-Host "  weapon_hadi_yolo.pt  $sz MB   OK" -ForegroundColor Green
} else {
    Write-Host "  weapon_hadi_yolo.pt  MISSING — run: git lfs pull" -ForegroundColor Red
}

Write-Host "`n=== Demo Videos Check ===" -ForegroundColor Cyan
@("demo_assets\videos\Wq0BuA8GM84_0.avi",
  "demo_assets\videos\YDOJvzChqSg_0 (1).avi",
  "demo_assets\videos\FXC43fACfPc_0.avi") | ForEach-Object {
    if (Test-Path $_) {
        Write-Host "  $((Split-Path $_ -Leaf).PadRight(30))  OK" -ForegroundColor Green
    } else {
        Write-Host "  $((Split-Path $_ -Leaf).PadRight(30))  MISSING — run: git lfs pull" -ForegroundColor Red
    }
}
