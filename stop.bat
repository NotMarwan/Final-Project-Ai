@echo off
title AI Sentinel - Stopping...
cd /d "%~dp0"

echo ========================================
echo   AI SENTINEL - Stopping...
echo ========================================
echo.

:: ── Kill processes on port 8002 (Backend) ────────────────────
echo [1/2] Stopping Backend (port 8002)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8002" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo       Backend stopped.

:: ── Kill processes on port 3000 (Frontend) ────────────────────
echo [2/2] Stopping Frontend (port 3000)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo       Frontend stopped.

echo.
echo ========================================
echo   AI SENTINEL STOPPED
echo ========================================
echo.
pause
