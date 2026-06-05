@echo off
REM Universal AI System - Quick Start Launcher
REM Works on Windows 10/11

setlocal enabledelayedexpansion

echo.
echo ========================================
echo  UNIVERSAL AI SYSTEM v1.0
echo  Quick Start Launcher
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found!
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

echo [OK] Python found
echo.

REM Check Ollama
ollama --version >nul 2>&1
if errorlevel 1 (
    echo WARNING: Ollama not found!
    echo Download from: https://ollama.com/download
    echo.
    choice /C YN /M "Continue anyway?"
    if errorlevel 2 exit /b 0
)

echo [OK] Ollama found
echo.

REM Check installed flag
if not exist ".installed.flag" (
    echo [SETUP] First run - installing dependencies...
    python ai_universal_system.py --setup
    if errorlevel 1 (
        echo Setup failed!
        pause
        exit /b 1
    )
    echo [OK] Setup complete
    echo.
)

REM Run system
echo Starting Universal AI System...
echo Type 'help' for commands
echo.

python ai_universal_system.py

pause
