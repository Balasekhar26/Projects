@echo off
title Kattappa AI System Assistant
color 0B

echo ========================================
echo  Kattappa AI System Assistant Launcher
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
echo Starting Kattappa AI System Assistant...
echo.
echo The application will open in your default browser
echo Features: Multi-agent coordination, AI tools, Chat interface
echo Press Ctrl+C to stop the server
echo.

call npm run dev

pause
