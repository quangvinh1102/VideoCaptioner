@echo off
chcp 65001 >nul
title VideoCaptioner
cd /d "%~dp0"

echo.
echo ========================================
echo   VideoCaptioner - Dang mo giao dien...
echo ========================================
echo.

:: Them uv + ffmpeg vao PATH (neu co)
set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\uv\bin;%PATH%"

:: Tim ffmpeg tu WinGet neu chua co trong PATH
where ffmpeg >nul 2>&1
if errorlevel 1 (
  for /f "delims=" %%i in ('dir /s /b "%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg.exe" 2^>nul') do (
    set "FFMPEG_DIR=%%~dpi"
    goto :found_ffmpeg
  )
)
:found_ffmpeg
if defined FFMPEG_DIR set "PATH=%FFMPEG_DIR%;%PATH%"

:: Kiem tra uv
where uv >nul 2>&1
if errorlevel 1 (
  echo [LOI] Khong tim thay "uv".
  echo Cai dat: powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
  echo.
  pause
  exit /b 1
)

:: Dam bao moi truong Python 3.12 + deps
if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Lan dau chay - dang cai dat moi truong...
  uv sync --python 3.12
  if errorlevel 1 (
    echo [LOI] Cai dat that bai.
    pause
    exit /b 1
  )
)

echo [OK] Mo VideoCaptioner GUI...
uv run videocaptioner gui
if errorlevel 1 (
  echo.
  echo Ung dung thoat voi loi.
  pause
)
