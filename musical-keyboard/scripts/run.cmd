@echo off
setlocal
cd /d "%~dp0.."

set "MODE=%~1"
if /I "%MODE%"=="help" goto help
if /I "%MODE%"=="/?" goto help
if /I "%MODE%"=="status" goto status

call :ensure_setup
if errorlevel 1 exit /b 1

call npm run dev
exit /b %errorlevel%

:ensure_setup
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is required. Install Node.js from https://nodejs.org and rerun setup.bat.
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo npm is required and normally installs with Node.js.
  exit /b 1
)
if exist "node_modules\" exit /b 0
echo First run setup required. Installing Musical Keyboard dependencies...
call "%CD%\setup.bat" --setup-only
exit /b %errorlevel%

:status
if exist "setup.bat" (echo setup.bat: ready) else (echo setup.bat: missing & exit /b 1)
if exist "run.exe" (echo run.exe: ready) else (echo run.exe: missing & exit /b 1)
if exist "node_modules\" (echo node_modules: ready) else (echo node_modules: missing - run setup.bat)
exit /b 0

:help
echo Musical Keyboard launcher
echo.
echo Commands:
echo   run.exe         Start dev app
echo   run.exe status  Check setup/run files
echo   run.exe help    Show this help
exit /b 0
