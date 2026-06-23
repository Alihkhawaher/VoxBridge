@echo off
title VoxBridge
echo Starting Voice Server...
echo Open http://127.0.0.1:7790/ in your browser
echo.
stt-env\Scripts\python.exe voice-server.py
if errorlevel 1 (
    echo.
    echo [ERROR] Voice Server exited with an error.
    pause
)