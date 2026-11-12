@echo off
title Stop YouTube Downloader Server
echo ========================================================
echo   Stopping YouTube Downloader Background Server...
echo ========================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }; Write-Host 'Server on port 8000 has been stopped successfully.' -ForegroundColor Green"

echo.
echo ========================================================
echo Done! You can close this window now.
echo ========================================================
timeout /t 3 >nul
