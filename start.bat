@echo off
title AI Sentinel - Starting...
cd /d "%~dp0"

echo ========================================
echo   AI SENTINEL - Starting...
echo ========================================
echo.

:: ── Check if already running ─────────────────────────────────
netstat -ano | findstr ":8002" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo [WARN] Port 8002 already in use. Backend may already be running.
    echo        Run stop.bat first if you want to restart.
    echo.
)

:: ── Activate Python venv ─────────────────────────────────────
if exist "backend\venv\Scripts\activate.bat" (
    call backend\venv\Scripts\activate.bat
)

:: ── Start Backend ─────────────────────────────────────────────
echo [1/2] Starting Backend (FastAPI on port 8002)...
start /min "AI Sentinel Backend" cmd /c "cd backend && python -m uvicorn api:app --host 0.0.0.0 --port 8002"

:: ── Wait for backend to be ready ─────────────────────────────
echo       Waiting for backend to initialize...
set /a COUNT=0
:WAIT_BACKEND
timeout /t 1 /nobreak >nul
set /a COUNT+=1
if %COUNT% GEQ 30 (
    echo       [WARN] Backend may not be ready yet. Continuing anyway...
    goto START_FRONTEND
)
curl -s http://localhost:8002/health >nul 2>&1
if %errorlevel% neq 0 (
    goto WAIT_BACKEND
)
echo       Backend ready!
echo.

:START_FRONTEND
:: ── Start Frontend ────────────────────────────────────────────
echo [2/2] Starting Frontend (Next.js on port 3000)...
start /min "AI Sentinel Frontend" cmd /c "npx next dev --port 3000"

:: ── Wait for frontend to be ready ────────────────────────────
echo       Waiting for frontend to initialize...
set /a COUNT=0
:WAIT_FRONTEND
timeout /t 1 /nobreak >nul
set /a COUNT+=1
if %COUNT% GEQ 30 (
    echo       [WARN] Frontend may not be ready yet. Continuing anyway...
    goto OPEN_BROWSER
)
curl -s http://localhost:3000 >nul 2>&1
if %errorlevel% neq 0 (
    goto WAIT_FRONTEND
)
echo       Frontend ready!
echo.

:OPEN_BROWSER
:: ── Open browser ──────────────────────────────────────────────
echo Opening browser...
timeout /t 2 /nobreak >nul
start http://localhost:3000

echo.
echo ========================================
echo   AI SENTINEL IS RUNNING!
echo ========================================
echo.
echo   Dashboard:  http://localhost:3000
echo   Backend API: http://localhost:8002
echo   Health:     http://localhost:8002/health
echo.
echo   To stop: run stop.bat
echo.
pause
