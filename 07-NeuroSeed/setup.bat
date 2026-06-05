@echo off
setlocal
cd /d "%~dp0"

if not exist "prototype\index.html" (
  echo Missing prototype\index.html.
  exit /b 1
)

echo NeuroSeed setup complete. No install step is required.
exit /b 0
