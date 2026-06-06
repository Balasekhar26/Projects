@echo off
setlocal
cd /d "%~dp0.."

set "MODE=%~1"
if /I "%MODE%"=="help" goto help
if /I "%MODE%"=="/?" goto help
if /I "%MODE%"=="status" goto status

if not exist "node_modules\" (
  echo Dependencies are missing. Run setup.bat first.
  exit /b 1
)

call npm run build
if errorlevel 1 exit /b 1

call npm start
exit /b %errorlevel%

:status
if exist "setup.bat" (echo setup.bat: ready) else (echo setup.bat: missing & exit /b 1)
if exist "run.exe" (echo run.exe: ready) else (echo run.exe: missing & exit /b 1)
if exist "node_modules\" (echo node_modules: ready) else (echo node_modules: missing - run setup.bat)
exit /b 0

:help
echo PCB Doctor launcher
echo.
echo Commands:
echo   run.exe         Build and start app
echo   run.exe status  Check setup/run files
echo   run.exe help    Show this help
exit /b 0
