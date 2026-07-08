@echo off
title Kattappa AI System - Desktop App
color 0A

echo ==========================================
echo  Kattappa AI System - Desktop Application
echo ==========================================
echo.

cd /d "%~dp0"

echo Checking Node.js installation...
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed!
    echo Please install Node.js from https://nodejs.org
    pause
    exit /b 1
)

echo Node.js is installed
echo.

echo Checking desktop app dependencies...
if not exist "package.json" (
    echo ERROR: package.json not found in this folder.
    pause
    exit /b 1
)

echo Starting Kattappa AI System desktop app...
echo.
echo Features:
echo - Multi-agent AI interface
echo - Conversation and chat
echo - Performance monitoring
echo - Tool integration
echo.
echo Press Ctrl+C to stop the app
echo.

if not exist "ai-assistant\dist\index.html" (
    echo Building AI assistant frontend...
    pushd ai-assistant
    npm install --legacy-peer-deps --no-audit
    npm run build
    popd
)

set "NODE_ENV=production"
npm start

pause
