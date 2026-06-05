@echo off
setlocal
cd /d "%~dp0"

if not exist "node_modules\" (
  echo Dependencies are missing. Run setup.bat first.
  exit /b 1
)

call npm run build
if errorlevel 1 exit /b 1

call npm start
exit /b %errorlevel%
