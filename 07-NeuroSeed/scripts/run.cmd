@echo off
setlocal
cd /d "%~dp0.."

set "MODE=%~1"
if /I "%MODE%"=="help" goto help
if /I "%MODE%"=="/?" goto help
if /I "%MODE%"=="status" goto status

if not exist "prototype\index.html" (
  echo Missing prototype\index.html. Run setup.bat to check the project.
  exit /b 1
)

start "" "%CD%\prototype\index.html"
exit /b 0

:status
if exist "setup.bat" (echo setup.bat: ready) else (echo setup.bat: missing & exit /b 1)
if exist "run.exe" (echo run.exe: ready) else (echo run.exe: missing & exit /b 1)
if exist "prototype\index.html" (echo prototype: ready) else (echo prototype: missing & exit /b 1)
exit /b 0

:help
echo NeuroSeed launcher
echo.
echo Commands:
echo   run.exe         Open local prototype
echo   run.exe status  Check setup/run files
echo   run.exe help    Show this help
exit /b 0
