@echo off
setlocal
cd /d "%~dp0.."

set "MODE=%~1"
if /I "%MODE%"=="help" goto help
if /I "%MODE%"=="/?" goto help
if /I "%MODE%"=="status" goto status

call :ensure_setup
if errorlevel 1 exit /b 1

where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python is missing. NeuroSeed needs Python for the local memory backend.
    exit /b 1
  )
  start "NeuroSeed Memory" /min py "%CD%\backend\server.py"
) else (
  start "NeuroSeed Memory" /min python "%CD%\backend\server.py"
)

start "" "%CD%\prototype\index.html"
exit /b 0

:ensure_setup
call "%CD%\setup.bat" --setup-only
if errorlevel 1 exit /b 1
if not exist "prototype\index.html" (
  echo Missing prototype\index.html. Run setup.bat to check the project.
  exit /b 1
)
if not exist "backend\server.py" (
  echo Missing backend\server.py. Run setup.bat to check the project.
  exit /b 1
)
if not exist "backend\memory_store.py" (
  echo Missing backend\memory_store.py. Run setup.bat to check the project.
  exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python 3 is required. Install Python, then rerun setup.bat.
    exit /b 1
  )
)
if not exist "runtime" mkdir runtime
exit /b 0

:status
if exist "setup.bat" (echo setup.bat: ready) else (echo setup.bat: missing & exit /b 1)
if exist "run.exe" (echo run.exe: ready) else (echo run.exe: missing & exit /b 1)
if exist "prototype\index.html" (echo prototype: ready) else (echo prototype: missing & exit /b 1)
if exist "backend\server.py" (echo memory backend: ready) else (echo memory backend: missing & exit /b 1)
exit /b 0

:help
echo NeuroSeed launcher
echo.
echo Commands:
echo   run.exe         Start local memory backend and open prototype
echo   run.exe status  Check setup/run files
echo   run.exe help    Show this help
exit /b 0
