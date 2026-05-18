@echo off
title AI Sentinel - Stopping...
cd /d "%~dp0"

echo ========================================
echo   AI SENTINEL - Stopping...
echo ========================================
echo.

:: Kill by window title (set in start.bat)
taskkill /FI "WINDOWTITLE eq AI Sentinel Backend" /F >nul 2>&1
if %errorlevel%==0 (echo [OK] Backend stopped.) else (echo [INFO] Backend was not running.)

taskkill /FI "WINDOWTITLE eq AI Sentinel Frontend" /F >nul 2>&1
if %errorlevel%==0 (echo [OK] Frontend stopped.) else (echo [INFO] Frontend was not running.)

:: Also free the ports if something lingered
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8002" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo [OK] Freed port 8002 (PID %%a)
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo [OK] Freed port 3000 (PID %%a)
)

echo.
echo All processes stopped.
pause
