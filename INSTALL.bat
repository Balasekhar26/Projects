@echo off
setlocal EnableExtensions EnableDelayedExpansion

:: ============================================================
::  ULT — Universal Language Translator
::  Double-click installer for Windows
::  Right-click > Run as administrator
:: ============================================================

set "ROOT=%~dp0"
cd /d "%ROOT%"
set "FAILED=0"

title ULT Installer

echo.
echo  ============================================================
echo   Universal Language Translator  --  Windows Installer
echo  ============================================================
echo.

:: ── 1. Require Administrator ─────────────────────────────────
net session >nul 2>nul
if errorlevel 1 (
  echo  [!] This installer needs Administrator rights.
  echo      Right-click INSTALL.bat and choose "Run as administrator".
  echo.
  pause
  exit /b 1
)
echo  [ok] Running as Administrator

:: ── 2. Check winget ──────────────────────────────────────────
where winget >nul 2>nul
if errorlevel 1 (
  echo  [!] winget not found.
  echo      Install "App Installer" from the Microsoft Store, then re-run.
  pause
  exit /b 1
)
echo  [ok] winget found

:: ── 3. Install Node.js LTS if missing ────────────────────────
where node >nul 2>nul
if errorlevel 1 (
  echo  [install] Node.js LTS ...
  winget install -e --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo  [error] Node.js install failed.
    set "FAILED=1"
    goto :done
  )
  set "PATH=%ProgramFiles%\nodejs;%PATH%"
  echo  [ok] Node.js installed
) else (
  echo  [ok] Node.js already installed
)

where node >nul 2>nul
if errorlevel 1 (
  echo  [!] Node.js installed but not on PATH yet.
  echo      Close this window, open a NEW Administrator Command Prompt, and run INSTALL.bat again.
  pause
  exit /b 1
)

:: ── 4. Install npm dependencies ──────────────────────────────
echo.
echo  [run] npm install  (may take a few minutes) ...
call npm install
if errorlevel 1 (
  echo  [error] npm install failed.
  set "FAILED=1"
  goto :done
)
echo  [ok] npm packages installed

:: ── 5. Bootstrap runtime directories ─────────────────────────
echo.
echo  [run] Bootstrapping runtime ...
call npm run bootstrap:runtime
if errorlevel 1 (
  echo  [error] Runtime bootstrap failed.
  set "FAILED=1"
  goto :done
)
echo  [ok] Runtime directories ready

:: ── 6. Create .env if not present ────────────────────────────
if not exist "%ROOT%.env" (
  if exist "%ROOT%.env.example" (
    copy /Y "%ROOT%.env.example" "%ROOT%.env" >nul
    echo  [ok] .env created  --  edit it to add OPENAI_API_KEY for online mode
  )
) else (
  echo  [ok] .env already exists
)

:: ── 7. Write launch.bat ───────────────────────────────────────
set "LAUNCHER=%ROOT%launch.bat"
(
  echo @echo off
  echo cd /d "%ROOT%"
  echo node_modules\.bin\electron electron\main.js
) > "%LAUNCHER%"
echo  [ok] Launcher written

:: ── 8. Create Desktop shortcut ───────────────────────────────
echo.
echo  [run] Creating desktop shortcut ...

set "SHORTCUT=%USERPROFILE%\Desktop\ULT Translator.lnk"
set "ELECTRON_EXE=%ROOT%node_modules\electron\dist\electron.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%LAUNCHER%'; $s.WorkingDirectory = '%ROOT%'; $s.WindowStyle = 1; if (Test-Path '%ELECTRON_EXE%') { $s.IconLocation = '%ELECTRON_EXE%,0' }; $s.Description = 'Universal Language Translator'; $s.Save()"

if exist "%SHORTCUT%" (
  echo  [ok] Desktop shortcut created
) else (
  echo  [warn] Shortcut creation failed -- you can still run: npm run electron
)

:: ── 9. VB-CABLE reminder ─────────────────────────────────────
echo.
echo  ============================================================
echo   IMPORTANT -- Virtual Audio Driver required
echo   For system speaker interception install VB-Audio CABLE:
echo   https://vb-audio.com/Cable/
echo   Install it and reboot before using Speaker Intercept mode.
echo  ============================================================

:done
echo.
if "%FAILED%"=="1" (
  echo  [!!] Installation failed. See errors above.
  pause
  exit /b 1
)

echo  [done] Installation complete!
echo         Double-click "ULT Translator" on your Desktop to launch.
echo.
set /p "LAUNCH=Launch the app now? (Y/N): "
if /I "%LAUNCH%"=="Y" (
  start "" "%LAUNCHER%"
)
pause
exit /b 0
