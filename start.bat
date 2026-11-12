@echo off
title YouTube Downloader and Converter
echo ========================================================
echo   Starting YouTube MP3 / MP4 Converter Web App...
echo ========================================================

:: Ensure Python and FFmpeg are in PATH
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin;%PATH%"

cd /d "%~dp0"

echo Opening Web Browser at http://127.0.0.1:8000 ...
start "" "http://127.0.0.1:8000"

echo Starting server...
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

pause
