@echo off
title Musical Keyboard App
color 0E

echo ========================================
echo      Musical Keyboard App Launcher
echo ========================================
echo.

cd /d "%~dp0"

echo Checking Flutter installation...
flutter --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Flutter is not installed!
    echo Please install Flutter from https://flutter.dev/docs/get-started/install
    pause
    exit /b 1
)

echo Flutter is installed
echo.

echo Getting dependencies...
call flutter pub get
if errorlevel 1 (
    echo ERROR: Failed to get dependencies
    pause
    exit /b 1
)

echo.
echo Dependencies installed successfully!
echo.
echo Starting Musical Keyboard App...
echo.
echo This will launch the app in your default browser
echo Press Ctrl+C to stop the server
echo.

call flutter run -d web-server --web-port 3000

pause
