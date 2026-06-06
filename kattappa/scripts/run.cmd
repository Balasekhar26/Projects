@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
if not exist "runtime" mkdir runtime
if not exist "logs" mkdir logs

set "MODE=%~1"
if "%MODE%"=="" set "MODE=run"

if /I "%MODE%"=="run" goto run
if /I "%MODE%"=="start" goto run
if /I "%MODE%"=="desktop" goto run
if /I "%MODE%"=="services" goto services
if /I "%MODE%"=="backend" goto backend
if /I "%MODE%"=="backend-foreground" goto backend_foreground
if /I "%MODE%"=="ui" goto ui
if /I "%MODE%"=="ui-foreground" goto ui_foreground
if /I "%MODE%"=="dev" goto dev
if /I "%MODE%"=="build" goto build
if /I "%MODE%"=="status" goto status
if /I "%MODE%"=="stop" goto stop
if /I "%MODE%"=="help" goto help
if /I "%MODE%"=="/?" goto help

echo Unknown option: %MODE%
goto help

:run
echo Starting Kattappa AI OS on Windows...
call :ensure_setup
if errorlevel 1 exit /b 1
call :start_ollama_if_available
call :ensure_backend
if errorlevel 1 exit /b 1
call :wait_backend
if errorlevel 1 exit /b 1
call :open_app
exit /b %errorlevel%

:services
echo Starting Kattappa AI OS services...
call :ensure_setup
if errorlevel 1 exit /b 1
call :start_ollama_if_available
call :ensure_backend
if errorlevel 1 exit /b 1
call :wait_backend
exit /b %errorlevel%

:backend
call :ensure_setup
if errorlevel 1 exit /b 1
call :ensure_backend
if errorlevel 1 exit /b 1
call :wait_backend
exit /b %errorlevel%

:backend_foreground
call :ensure_setup
if errorlevel 1 exit /b 1
"%PROJECT_ROOT%\ai_system_env\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%

:ui
call :start_web_ui
exit /b %errorlevel%

:ui_foreground
cd /d "%PROJECT_ROOT%\apps\desktop"
npm run dev
exit /b %errorlevel%

:dev
call :ensure_setup
if errorlevel 1 exit /b 1
call :start_ollama_if_available
call :ensure_backend
if errorlevel 1 exit /b 1
cd /d "%PROJECT_ROOT%\apps\desktop"
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
npm run tauri:dev
exit /b %errorlevel%

:build
call :ensure_setup
if errorlevel 1 exit /b 1
cd /d "%PROJECT_ROOT%\apps\desktop"
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
npm install
npm run tauri:build:windows-msi
exit /b %errorlevel%

:status
echo Checking Kattappa AI OS backend...
if exist "setup.bat" (echo setup.bat: ready) else (echo setup.bat: missing & exit /b 1)
if exist "run.exe" (echo run.exe: ready) else (echo run.exe: missing & exit /b 1)
if exist "ai_system_env\Scripts\python.exe" (echo python env: ready) else (echo python env: missing - run setup.bat)
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:8000/ready' -TimeoutSec 3 | Out-Null; Write-Host 'backend: online at http://127.0.0.1:8000'; try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 15; $r | ConvertTo-Json -Depth 5 } catch { Write-Host 'backend: ready, detailed health slow' } } catch { Write-Host 'backend: offline (normal if app is not running)' }"
exit /b 0

:stop
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\scripts\Shutdown_Kattappa_AI_OS.ps1"
exit /b %errorlevel%

:help
echo.
echo Kattappa AI OS Windows launcher
echo.
echo Supported commands:
echo   setup.bat         First setup only
echo   run.exe           Run app
echo   run.exe services  Start backend/services only
echo   run.exe backend   Start backend only
echo   run.exe ui        Open browser desktop UI
echo   run.exe dev       Start backend + Tauri dev app
echo   run.exe build     Build native Windows desktop app
echo   run.exe status    Check launcher/backend health
echo   run.exe stop      Stop Kattappa AI OS services
echo.
exit /b 0

:ensure_setup
if exist "ai_system_env\Scripts\python.exe" (
  if exist "backend\.env" exit /b 0
)
echo First run setup required. Installing Kattappa AI OS for this machine...
call "%PROJECT_ROOT%\setup.bat" --setup-only
if errorlevel 1 exit /b 1
exit /b 0

:start_ollama_if_available
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama not found. Continuing; local model chat will show unavailable until Ollama is installed.
  exit /b 0
)
netstat -ano | findstr /R /C:":11434 .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo Ollama already running. Reusing it.
  exit /b 0
)
echo Starting Ollama...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$runtime='%PROJECT_ROOT%\runtime'; if(!(Test-Path $runtime)){New-Item -ItemType Directory -Path $runtime | Out-Null}; $p=Start-Process -WindowStyle Hidden -FilePath 'ollama' -ArgumentList 'serve' -PassThru; Set-Content -LiteralPath (Join-Path $runtime 'ollama.pid') -Value $p.Id; Set-Content -LiteralPath (Join-Path $runtime 'ollama-started-by-kattappa.flag') -Value (Get-Date -Format o)"
exit /b 0

:ensure_backend
echo Checking backend at http://127.0.0.1:8000
curl.exe --fail --silent --max-time 2 http://127.0.0.1:8000/ready >nul 2>nul
if not errorlevel 1 (
  echo Backend already running. Reusing it.
  exit /b 0
)
if not exist "ai_system_env\Scripts\python.exe" (
  echo Python environment missing: ai_system_env\Scripts\python.exe
  exit /b 1
)
echo Starting backend...
if exist "ai_system_env\Scripts\pythonw.exe" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -WindowStyle Hidden -FilePath '%PROJECT_ROOT%\ai_system_env\Scripts\pythonw.exe' -ArgumentList '%PROJECT_ROOT%\backend\run_server.py' -PassThru; Set-Content -LiteralPath '%PROJECT_ROOT%\runtime\backend.pid' -Value $p.Id"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -WindowStyle Hidden -FilePath '%PROJECT_ROOT%\ai_system_env\Scripts\python.exe' -ArgumentList '%PROJECT_ROOT%\backend\run_server.py' -PassThru; Set-Content -LiteralPath '%PROJECT_ROOT%\runtime\backend.pid' -Value $p.Id"
)
exit /b 0

:wait_backend
echo Waiting for backend readiness...
for /L %%I in (1,1,45) do (
  curl.exe --fail --silent --max-time 2 http://127.0.0.1:8000/ready >nul 2>nul
  if not errorlevel 1 (
    echo Backend ready.
    exit /b 0
  )
  <nul set /p "=."
  ping -n 2 127.0.0.1 >nul
)
echo.
echo Backend did not become ready within 45 seconds.
echo Last backend log:
if exist "logs\backend-launch.log" type "logs\backend-launch.log"
if exist "logs\backend-launch.err.log" type "logs\backend-launch.err.log"
exit /b 1

:open_app
if exist "apps\desktop\src-tauri\target\release\kattappa-ai-os-desktop.exe" (
  echo Opening native desktop app...
  start "" "%PROJECT_ROOT%\apps\desktop\src-tauri\target\release\kattappa-ai-os-desktop.exe"
  exit /b 0
)
echo Native desktop app is not built yet. Opening browser desktop UI instead.
call :start_web_ui
exit /b %errorlevel%

:start_web_ui
where npm >nul 2>nul
if errorlevel 1 (
  echo npm not found. Install Node.js to run the desktop UI, or build the native app on a machine with Node installed.
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$listen=Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue; if($listen){ exit 0 }; exit 1"
if errorlevel 1 (
  if not exist "apps\desktop\node_modules" (
    echo Installing desktop UI packages...
    cd /d "%PROJECT_ROOT%\apps\desktop"
    npm install
    if errorlevel 1 exit /b 1
    cd /d "%PROJECT_ROOT%"
  )
  echo Starting browser desktop UI...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -WindowStyle Hidden -FilePath $env:ComSpec -ArgumentList '/c', '\"%~f0\" ui-foreground'"
)
echo Waiting for browser desktop UI...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 45;$i++){ try { $r=Invoke-WebRequest -Uri 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 2; if($r.StatusCode -lt 500){ $ok=$true; break } } catch {}; Start-Sleep -Seconds 1 }; if(-not $ok){ exit 1 }"
if errorlevel 1 (
  echo Browser desktop UI did not become ready. Try: run.bat dev
  exit /b 1
)
start "" "http://127.0.0.1:5173"
exit /b 0
