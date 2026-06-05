@echo off
setlocal
cd /d "%~dp0"

if not exist "prototype\index.html" (
  echo Missing prototype\index.html. Run setup.bat to check the project.
  exit /b 1
)

start "" "%~dp0prototype\index.html"
exit /b 0
