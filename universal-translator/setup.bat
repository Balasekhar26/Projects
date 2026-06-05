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

call npm run bootstrap:runtime
if errorlevel 1 exit /b 1

if not exist ".env" (
  if exist ".env.example" copy /Y ".env.example" ".env" >nul
)

echo Universal Translator setup complete.
exit /b 0
