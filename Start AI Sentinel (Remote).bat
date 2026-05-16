@echo off
title AI Sentinel - Starting...
cd /d "%~dp0"

echo Starting Backend...
start /min "AI Sentinel Backend" cmd /c "cd backend && python -m uvicorn api:app --host 0.0.0.0 --port 8002"

timeout /t 3 /nobreak >nul

echo Starting Frontend...
start /min "AI Sentinel Frontend" cmd /c "node .\node_modules\next\dist\bin\next dev"

timeout /t 3 /nobreak >nul

echo Starting Tunnel (look for URL in this window)...
start "AI Sentinel Tunnel" cmd /c "backend\cloudflared-windows-amd64.exe tunnel --url http://localhost:3000"

echo.
echo ========================================
echo   ALL 3 WINDOWS OPENED
echo ========================================
echo.
echo   Look for the "AI Sentinel Tunnel" window
echo   Find the URL like:
echo   https://xxxx.trycloudflare.com
echo.
echo   Open that URL on your Phone !
echo.
pause
