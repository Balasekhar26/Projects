@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SETUP_ONLY=0"
if /I "%~1"=="--setup-only" set "SETUP_ONLY=1"
if /I "%~1"=="help" goto help
if /I "%~1"=="--help" goto help
if /I "%~1"=="/?" goto help

if not exist "prototype\index.html" (
  echo Missing prototype\index.html.
  pause
  exit /b 1
)

if not exist "backend\server.py" (
  echo Missing backend\server.py.
  pause
  exit /b 1
)

if not exist "backend\memory_store.py" (
  echo Missing backend\memory_store.py.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python 3 is required for NeuroSeed's local memory backend.
    echo Install Python from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
  )
)

if not exist "runtime" mkdir runtime

echo NeuroSeed setup complete. Local memory uses built-in SQLite; ChromaDB is optional.
if "%SETUP_ONLY%"=="1" exit /b 0

echo Starting NeuroSeed...
call "%~dp0scripts\run.cmd"
exit /b %errorlevel%

:help
echo.
echo NeuroSeed setup
echo.
echo Double-click setup.bat to verify the local memory backend and open the prototype.
echo Use setup.bat --setup-only to verify files without launching.
echo Normal launches after setup use run.exe.
echo.
exit /b 0
