@echo off
setlocal
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is required. Install Node.js from https://nodejs.org and rerun setup.bat.
  exit /b 1
)

if not exist "node_modules\" (
  call npm install
  if errorlevel 1 exit /b 1
)

echo Musical Keyboard setup complete.
exit /b 0
