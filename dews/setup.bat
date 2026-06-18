@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SETUP_ONLY=0"
if /I "%~1"=="--setup-only" set "SETUP_ONLY=1"
if /I "%~1"=="help" goto help
if /I "%~1"=="--help" goto help
if /I "%~1"=="/?" goto help

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is required to set up DEWS Safe Simulation.
  echo Install Node.js from https://nodejs.org, then double-click setup.bat again.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo npm is required and normally installs with Node.js.
  echo Reinstall Node.js from https://nodejs.org, then double-click setup.bat again.
  pause
  exit /b 1
)

call npm run setup
if errorlevel 1 (
  echo DEWS setup failed.
  pause
  exit /b 1
)

echo DEWS setup complete.
if "%SETUP_ONLY%"=="1" exit /b 0

echo Starting DEWS Safe Simulation...
call "%~dp0scripts\run.cmd"
exit /b %errorlevel%

:help
echo.
echo DEWS Safe Simulation setup
echo.
echo Double-click setup.bat to install dependencies and start the app.
echo Use setup.bat --setup-only to install dependencies without launching.
echo Normal launches after setup use run.exe.
echo.
exit /b 0
