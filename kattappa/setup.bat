@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "SETUP_ARGS=--accept-agreement --launch"
if /I "%~1"=="--setup-only" set "SETUP_ARGS="
if /I "%~1"=="--accept-agreement" set "SETUP_ARGS=--accept-agreement --launch"
if /I "%~1"=="--print-agreement" set "SETUP_ARGS=--print-agreement"
if /I "%~1"=="--help" goto help
if /I "%~1"=="/?" goto help

where py >nul 2>nul
if not errorlevel 1 (
  py -3 installer\setup_kattappa.py %SETUP_ARGS%
  exit /b %errorlevel%
)

where python >nul 2>nul
if not errorlevel 1 (
  python installer\setup_kattappa.py %SETUP_ARGS%
  exit /b %errorlevel%
)

echo Python 3 is required to install Kattappa AI OS.
echo Install Python from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
pause
exit /b 1

:help
echo.
echo Kattappa AI OS Windows installer
echo.
echo Usage:
echo   setup.bat
echo   setup.bat --print-agreement
echo   setup.bat --accept-agreement
echo.
echo Normal launches after setup use run.exe.
echo.
exit /b 0
