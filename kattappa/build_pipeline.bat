@echo off
echo =======================================
echo KATTAPPA UNIFIED BUILD VERIFICATION
echo =======================================

echo [1/3] Running Python Backend Unit Tests...
call ai_system_env\Scripts\python -m pytest backend/tests/test_rbil.py backend/tests/test_adaptive_runtime.py
if %errorlevel% neq 0 (
    echo [ERROR] Backend tests failed!
    exit /b 1
)

echo [2/3] Building Frontend Tauri Application...
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARN] npm is not installed. Skipping frontend Tauri build.
    goto skip_frontend
)

cd apps\desktop
call npm install
call npm run build
if %errorlevel% neq 0 (
    echo [ERROR] Frontend Tauri build failed!
    exit /b 1
)
cd ..\..

:skip_frontend

echo [3/3] Running Integration Macro Smoke Tests...
call ai_system_env\Scripts\python -m pytest backend/tests/test_macros.py
if %errorlevel% neq 0 (
    echo [ERROR] Smoke tests failed!
    exit /b 1
)

echo =======================================
echo BUILD VERIFICATION SUCCESSFUL
echo =======================================
exit /b 0
