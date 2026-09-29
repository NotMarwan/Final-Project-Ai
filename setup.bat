@echo off
title AI Sentinel - First Time Setup
cd /d "%~dp0"

echo ========================================
echo   AI SENTINEL - First Time Setup
echo ========================================
echo.

:: ── Check Python ──────────────────────────────────────────────
echo [1/6] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Download Python 3.10+ from https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo       Python %PY_VER% found.
echo.

:: ── Check Node.js ────────────────────────────────────────────
echo [2/6] Checking Node.js...
node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH.
    echo         Download Node.js 18+ from https://nodejs.org/
    pause
    exit /b 1
)
for /f %%v in ('node --version') do set NODE_VER=%%v
echo       Node.js %NODE_VER% found.
echo.

:: ── Create Python virtual environment ────────────────────────
echo [3/6] Setting up Python virtual environment...
if not exist "backend\venv" (
    python -m venv backend\venv
    echo       Virtual environment created.
) else (
    echo       Virtual environment already exists. Skipping.
)
echo.

:: ── Install Python dependencies ──────────────────────────────
echo [4/6] Installing Python dependencies (this may take a few minutes)...
call backend\venv\Scripts\activate.bat
pip install -r backend\requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [WARN] Some Python packages may have failed. Check the output above.
)
echo       Python dependencies installed.
echo.

:: ── Install Node.js dependencies ─────────────────────────────
echo [5/6] Installing Node.js dependencies...
if not exist "node_modules" (
    npm install --silent
) else (
    echo       node_modules already exists. Running npm install to update...
    npm install --silent
)
echo       Node.js dependencies installed.
echo.

:: ── Create .env files from templates ─────────────────────────
echo [6/6] Setting up environment files...
if not exist "backend\.env" (
    copy "backend\.env.example" "backend\.env" >nul
    echo       backend\.env created from template.
    echo       [ACTION REQUIRED] Edit backend\.env with your API keys:
    echo         - GROQ_API_KEY (for AI reports)
    echo         - OPENROUTER_API_KEY (for DeepSeek reports)
    echo         - TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (for alerts)
) else (
    echo       backend\.env already exists. Skipping.
)

if not exist ".env.local" (
    copy ".env.local.example" ".env.local" >nul
    echo       .env.local created from template.
) else (
    echo       .env.local already exists. Skipping.
)
echo.

:: ── Check model weights ──────────────────────────────────────
echo Checking AI model weights...
set MODELS_OK=1
if not exist "backend\best_model.pt" (
    echo   [MISSING] backend\best_model.pt - Violence detection model
    set MODELS_OK=0
)
if not exist "backend\weapon_yolo.pt" (
    echo   [MISSING] backend\weapon_yolo.pt - Weapon detection model
    set MODELS_OK=0
)
if %MODELS_OK%==0 (
    echo.
    echo   [IMPORTANT] You need model weights to run AI detection.
    echo   Contact your instructor or download from the shared drive.
    echo   Place the .pt files in the backend\ folder.
    echo.
)
echo.

:: ── Done ─────────────────────────────────────────────────────
echo ========================================
echo   SETUP COMPLETE!
echo ========================================
echo.
echo   Next steps:
echo   1. Edit backend\.env with your API keys (optional for demo)
echo   2. Make sure model weights are in backend\ (if using AI detection)
echo   3. Run start.bat to launch the application
echo.
echo   To launch: double-click start.bat
echo.
pause
