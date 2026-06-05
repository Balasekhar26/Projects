@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  Projects workspace verification
echo ========================================
echo.

call :RUN "AI Cyber Shield web build" "ai-cyber-shield" "npm run build"
call :RUN "Musical Keyboard web build" "musical-keyboard" "npm run build"
call :RUN "DEWS web build" "dews" "npm run build"
call :RUN "PCB Doctor web build" "pcb-doctor" "npm run build"
call :RUN "Universal Translator tests" "universal-translator" "npm run test -- --test-reporter=spec"
call :RUN "Universal AI desktop build" "universal-ai\apps\desktop" "npm run build"

if exist "universal-ai\ai_system_env\Scripts\python.exe" (
  call :RUN "Universal AI backend tests" "universal-ai" "ai_system_env\Scripts\python.exe -m pytest backend\tests tests -q"
) else (
  echo [skip] Universal AI Python environment not found at universal-ai\ai_system_env\Scripts\python.exe
)

call :RUN_PYTEST_STANDALONE "DEWS engine tests" "dews"
call :RUN_PYTEST_STANDALONE "PCB Doctor engine tests" "pcb-doctor"

echo.
echo Verification finished.
pause
exit /b 0

:RUN
echo.
echo [%~1]
pushd "%~2"
call %~3
if errorlevel 1 (
  echo [fail] %~1
  popd
  pause
  exit /b 1
)
popd
echo [ok] %~1
exit /b 0

:RUN_PYTEST_STANDALONE
echo.
echo [%~1]
if exist "%~2\test.bat" (
  pushd "%~2"
  call test.bat
  if errorlevel 1 (
    echo [fail] %~1
    popd
    pause
    exit /b 1
  )
  popd
  echo [ok] %~1
  exit /b 0
)
if exist "%~2\venv\Scripts\python.exe" (
  call :RUN "%~1" "%~2" "venv\Scripts\python.exe -m pytest tests -q"
  exit /b %errorlevel%
)
echo [skip] %~1 requires %~2\test.bat or %~2\venv\Scripts\python.exe
exit /b 0
