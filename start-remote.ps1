param(
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Host.UI.RawUI.WindowTitle = "AI Sentinel - Remote Access"

function Log($m) { Write-Host "[AI Sentinel] $m" -ForegroundColor Cyan }
function Ok($m)  { Write-Host "[OK] $m" -ForegroundColor Green }

Log "Starting AI Sentinel with Remote Access..."
Log ""

# Cleanup function
$cleanup = {
  Log "Shutting down..."
  Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -eq "" } | Stop-Process -Force -ErrorAction SilentlyContinue
  Get-Process -Name "node" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -SupportEvent -Action $cleanup | Out-Null

# 1. Start Backend (new window, minimized)
Log "Starting Python Backend (port 8002)..."
$backendDir = Join-Path $ProjectRoot "backend"
$backendLog = Join-Path $ProjectRoot "backend-remote.log"
Start-Process -WindowStyle Minimized -FilePath "python" -ArgumentList "api.py" -WorkingDirectory $backendDir

$maxWait = 40
$ready = $false
for ($i = 1; $i -le $maxWait; $i++) {
  Start-Sleep -Seconds 1
  try { $r = Invoke-WebRequest -Uri "http://localhost:8002/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop; if ($r.StatusCode -eq 200) { $ready = $true; break } } catch {}
  Write-Host "  Waiting for backend... ($i/$maxWait)" -ForegroundColor DarkGray
}
if (-not $ready) { Write-Host "  [WARN] Backend may still be starting. Continuing..." -ForegroundColor Yellow }
else { Ok "Backend ready on port 8002" }

# 2. Start Frontend (new window, minimized)
Log "Starting Next.js Frontend (port 3000)..."
if (-not $SkipBuild) {
  Push-Location $ProjectRoot
  npm run build 2>&1 | Out-Null
  Pop-Location
}
Start-Process -WindowStyle Minimized -FilePath "npx" -ArgumentList "next dev" -WorkingDirectory $ProjectRoot

$ready = $false
for ($i = 1; $i -le 40; $i++) {
  Start-Sleep -Seconds 1
  try { $r = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop; if ($r.StatusCode -eq 200) { $ready = $true; break } } catch {}
  Write-Host "  Waiting for frontend... ($i/40)" -ForegroundColor DarkGray
}
if (-not $ready) { Write-Host "  [WARN] Frontend may still be starting. Continuing..." -ForegroundColor Yellow }
else { Ok "Frontend ready on port 3000" }

# 3. Start Cloudflare Tunnel
$cf = "$ProjectRoot\backend\cloudflared-windows-amd64.exe"
if (-not (Test-Path $cf)) {
  Write-Host "[ERROR] cloudflared not found at $cf" -ForegroundColor Red
  exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TUNNEL STARTING..." -ForegroundColor White
Write-Host "  Look for a URL like:" -ForegroundColor White
Write-Host "  https://xxxx.trycloudflare.com" -ForegroundColor Green
Write-Host "" -ForegroundColor White
Write-Host "  Open that URL on your PHONE browser" -ForegroundColor White
Write-Host "  Tap 'Install' or 'Add to Home Screen'" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

& $cf tunnel --url http://localhost:3000

Log "Tunnel closed."
