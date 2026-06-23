@echo off
setlocal
title VoxBridge Setup

:: ── Auto-elevate to admin (needed for Chocolatey) ───────────
net session >nul 2>&1
if errorlevel 1 (
    echo [INFO] Requesting administrator privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList '/k \"%~f0\"' -Verb RunAs"
    exit /b
)

:: Ensure we are in the script's directory
pushd "%~dp0"

:: ── Detect if running from temp (one-command install) ────────
set "PROJECT_DIR=%USERPROFILE%\VoxBridge"
if exist "voice-server.py" set "PROJECT_DIR=%cd%"

echo ============================================================
echo   VoxBridge - Automatic Setup
echo   STT (Faster-Whisper) + TTS (Supertonic)
echo   Install location: %PROJECT_DIR%
echo ============================================================
echo.

:: ── Step 1: Check ALL prerequisites ─────────────────────────
echo [Step 1/4] Checking prerequisites...
echo.

set "MISSING="

where python >nul 2>&1
if errorlevel 1 (
    echo   [X] Python     - NOT FOUND
    set "MISSING=1"
) else (
    echo   [OK] Python     - found
)

where git >nul 2>&1
if errorlevel 1 (
    echo   [X] Git        - NOT FOUND
    set "MISSING=1"
) else (
    echo   [OK] Git        - found
)

where git-lfs >nul 2>&1
if errorlevel 1 (
    echo   [X] Git LFS    - NOT FOUND
    set "MISSING=1"
) else (
    echo   [OK] Git LFS    - found
)

where uv >nul 2>&1
if errorlevel 1 (
    echo   [X] uv         - NOT FOUND
    set "MISSING=1"
) else (
    echo   [OK] uv         - found
)

echo.

:: ── Step 2: Install missing prerequisites via Chocolatey ────
if not defined MISSING (
    echo [Step 2/4] All prerequisites found. Skipping installation.
    goto :step3
)

echo [Step 2/4] Missing prerequisites detected. Installing via Chocolatey...
echo.

:: Check/install Chocolatey
where choco >nul 2>&1
if errorlevel 1 (
    echo   Installing Chocolatey...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    if errorlevel 1 (
        echo [ERROR] Failed to install Chocolatey.
        echo   Install manually from: https://chocolatey.org/install
        pause
        exit /b 1
    )
    set "PATH=%ALLUSERSPROFILE%\chocolatey\bin;%PATH%"
    echo   [OK] Chocolatey installed.
) else (
    echo   [OK] Chocolatey already installed.
)
echo.

:: Install only what's missing
where python >nul 2>&1
if errorlevel 1 (
    echo   Installing Python 3.11...
    choco install python311 -y
    set "PATH=C:\Python311;C:\Python311\Scripts;%PATH%"
    echo   [OK] Python installed.
)

where git >nul 2>&1
if errorlevel 1 (
    echo   Installing Git...
    choco install git -y
    set "PATH=C:\Program Files\Git\cmd;%PATH%"
    echo   [OK] Git installed.
)

where git-lfs >nul 2>&1
if errorlevel 1 (
    echo   Installing Git LFS...
    choco install git-lfs -y
    echo   [OK] Git LFS installed.
)

where uv >nul 2>&1
if errorlevel 1 (
    echo   Installing uv...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%LOCALAPPDATA%\uv\bin;%PATH%"
    echo   [OK] uv installed.
)

:: Initialize Git LFS
git lfs install >nul 2>&1

echo.
echo   All prerequisites installed.
echo.

:: ── Step 3: Get/update project files ────────────────────────
:step3
echo [Step 3/4] Getting project files...
echo.

if not exist "voice-server.py" goto :clone_project

REM Project files exist — check if it's a git repo for updates
if not exist ".git" goto :non_git
echo   VoxBridge already installed. Updating to latest...
git pull
echo   [OK] Updated.
goto :step4

:non_git
echo   VoxBridge already installed (non-git). Skipping clone.
goto :step4

:clone_project
echo   Cloning VoxBridge repository to %PROJECT_DIR%...
if not exist "%PROJECT_DIR%" mkdir "%PROJECT_DIR%"
cd /d "%PROJECT_DIR%"
git init
git remote add origin https://github.com/Alihkhawaher/VoxBridge.git
git fetch origin
git checkout -f master
if errorlevel 1 (
    echo [ERROR] Failed to clone repository.
    echo   Make sure Git is installed and try again.
    pause
    exit /b 1
)
echo   [OK] Repository cloned.

:step4
echo.

:: ── Step 4: Setup project ───────────────────────────────────
echo [Step 4/4] Setting up project...
echo.

:: Create venv
if exist "stt-env\Scripts\python.exe" (
    echo   Virtual environment already exists.
) else (
    echo   Creating virtual environment...
    uv venv stt-env --python 3.11
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo   [OK] Virtual environment created.
)

:: Install dependencies
echo   Installing Python packages from requirements.txt...
uv pip install --python stt-env\Scripts\python.exe -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo   [OK] Dependencies installed.
echo.

:: Download STT model
if exist "whisper-ar-en\model.bin" (
    echo   STT model already downloaded.
    goto :verify
)

echo   Downloading Arabic-English STT model (~1.5GB)...
echo   This may take several minutes depending on your internet speed.
echo.

git clone https://huggingface.co/Mano200600/faster-whisper-large-v2-ar-codeswitching whisper-ar-en
if not errorlevel 1 (
    echo   [OK] Model downloaded via git.
    goto :verify
)
echo   [WARN] git clone failed, trying huggingface_hub...
if exist "whisper-ar-en" rmdir /s /q whisper-ar-en

stt-env\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('Mano200600/faster-whisper-large-v2-ar-codeswitching', local_dir='whisper-ar-en')"
if errorlevel 1 (
    echo [ERROR] Failed to download model.
    echo   Try manually: git lfs install ^&^& git clone https://huggingface.co/Mano200600/faster-whisper-large-v2-ar-codeswitching whisper-ar-en
    pause
    exit /b 1
)
echo   [OK] Model downloaded.

:verify
echo.
echo ============================================================
echo   Verifying...
echo ============================================================
stt-env\Scripts\python.exe -c "from faster_whisper import WhisperModel; from supertonic import TTS; print('All imports OK')"
if errorlevel 1 (
    echo [ERROR] Verification failed.
    pause
    exit /b 1
)

:: ── Create desktop shortcut ─────────────────────────────────
echo.
echo   Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "create-shortcut.ps1"

echo.
echo ============================================================
echo   Setup complete!
echo.
echo   To start the server:
echo     Double-click the "VoxBridge" shortcut on your Desktop
echo     or double-click start.bat
echo     or run: stt-env\Scripts\python.exe voice-server.py
echo.
echo   Then open: http://127.0.0.1:7790/
echo ============================================================
echo.
pause