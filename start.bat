@echo off
title AI Sentinel - Starting...
cd /d "%~dp0"

echo ========================================
echo   AI SENTINEL - Starting...
echo ========================================
echo.

:: ── Check if already running ────────────────────────────────────
netstat -ano | findstr ":8002" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo [WARN] Port 8002 already in use. Run stop.bat first to restart cleanly.
    echo.
)

:: ── Detect venv ──────────────────────────────────────────────────
if exist "backend\venv\Scripts\activate.bat" (
    echo [Setup] Using backend\venv
    call backend\venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo [Setup] Using root venv
    call venv\Scripts\activate.bat
) else (
    echo [ERROR] No Python virtual environment found.
    echo         Run: python -m venv venv ^&^& venv\Scripts\pip install -r backend\requirements.txt
    pause
    exit /b 1
)

:: ── Start Backend ────────────────────────────────────────────────
echo [1/2] Starting Backend (port 8002)...
if exist "backend\startup.log" del "backend\startup.log"
start "AI Sentinel Backend" /min cmd /c "cd backend && python api.py > startup.log 2>&1"

:: ── Wait for backend ready (health check) ───────────────────────
echo       Waiting for backend (up to 45s)...
set /a COUNT=0
:WAIT_BACKEND
timeout /t 2 /nobreak >nul
set /a COUNT+=2
curl -sf http://localhost:8002/health >nul 2>&1
if %errorlevel%==0 goto BACKEND_READY
if %COUNT% GEQ 45 (
    echo [WARN] Backend health check timed out after %COUNT%s. Check backend\startup.log
    goto START_FRONTEND
)
echo       Still waiting... (%COUNT%s)
goto WAIT_BACKEND

:BACKEND_READY
echo       Backend ready in %COUNT%s!
echo.

:START_FRONTEND
:: ── Start Frontend ───────────────────────────────────────────────
echo [2/2] Starting Frontend (port 3000)...
start "AI Sentinel Frontend" /min cmd /c "npx next dev --port 3000 > frontend.out.log 2>&1"

:: ── Wait for frontend ready ─────────────────────────────────────
echo       Waiting for frontend (up to 30s)...
set /a COUNT=0
:WAIT_FRONTEND
timeout /t 2 /nobreak >nul
set /a COUNT+=2
curl -sf http://localhost:3000 >nul 2>&1
if %errorlevel%==0 goto FRONTEND_READY
if %COUNT% GEQ 30 (
    echo [WARN] Frontend timed out. Check frontend.out.log
    goto OPEN_BROWSER
)
echo       Still waiting... (%COUNT%s)
goto WAIT_FRONTEND

:FRONTEND_READY
echo       Frontend ready in %COUNT%s!

:OPEN_BROWSER
echo.
timeout /t 1 /nobreak >nul
start http://localhost:3000

echo.
echo ========================================
echo   AI SENTINEL IS RUNNING
echo ========================================
echo.
echo   Dashboard:   http://localhost:3000
echo   Backend:     http://localhost:8002
echo   Health:      http://localhost:8002/health
echo   Backend log: backend\startup.log
echo.
echo   To stop: run stop.bat
echo.
pause
