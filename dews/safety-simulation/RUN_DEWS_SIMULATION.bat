@echo off
title DEWS Safe-Domain Simulation
color 0D

echo ========================================
echo  DEWS Safe-Domain Simulation Launcher
echo ========================================
echo.

cd /d "%~dp0"

echo Checking Node.js installation...
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed!
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

echo Node.js is installed
echo.

echo Installing dependencies...
call npm install
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo Dependencies installed successfully!
echo.
echo Starting DEWS Safe-Domain Simulation...
echo.
echo The application will open in your default browser
echo Features: Energy monitoring, Safety simulation, Environment tracking
echo Press Ctrl+C to stop the server
echo.

call npm run dev

pause
