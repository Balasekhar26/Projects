@echo off
title Build Musical Keyboard EXE
color 0E

echo ========================================
echo Building Musical Keyboard EXE
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
echo Building for Windows...
call flutter build windows --release
if errorlevel 1 (
    echo ERROR: Windows build failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo     EXE BUILD SUCCESSFUL!
echo ========================================
echo.
echo Location: build\windows\x64\runner\Release\music_keyboard.exe
echo.
echo The EXE will auto-rebuild when you change source files!
echo.

if exist "build\windows\x64\runner\Release\music_keyboard.exe" (
    echo Opening EXE location...
    explorer "build\windows\x64\runner\Release"
) else (
    echo EXE file not found
    echo Check build logs above for errors
)

pause
