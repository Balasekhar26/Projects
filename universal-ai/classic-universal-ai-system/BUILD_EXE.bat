@echo off
title Build Universal AI System EXE
color 0B

echo ========================================
echo Building Universal AI System EXE
echo ========================================
echo.

cd /d "%~dp0"

echo Checking Node.js and Electron...
node --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Node.js is not installed!
    pause
    exit /b 1
)

echo Dependencies check...
if not exist "node_modules" (
    echo Installing dependencies...
    call npm install
)

echo.
echo Building AI assistant...
cd ai-assistant
call npm run build
if errorlevel 1 (
    echo ERROR: AI assistant build failed
    pause
    exit /b 1
)
cd ..

echo.
echo Building Electron app...
call npm run build:exe
if errorlevel 1 (
    echo ERROR: EXE build failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo     EXE BUILD SUCCESSFUL!
echo ========================================
echo.
echo Location: dist-exe\Universal AI System Setup.exe
echo.
echo The EXE will auto-rebuild when you change source files!
echo.

if exist "dist-exe\Universal AI System Setup.exe" (
    echo Opening EXE location...
    explorer "dist-exe"
) else (
    echo EXE file not found in dist-exe folder
    echo Check build logs above for errors
)

pause
