@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=setup"

if /I "%MODE%"=="help" goto :usage
if /I "%MODE%"=="--help" goto :usage
if /I "%MODE%"=="-h" goto :usage

set "INSTALL_ALLOWED=0"
if /I "%MODE%"=="setup" set "INSTALL_ALLOWED=1"
if /I "%MODE%"=="build-win" set "INSTALL_ALLOWED=1"
if /I "%MODE%"=="build-apk" set "INSTALL_ALLOWED=1"
if /I "%MODE%"=="build-aab" set "INSTALL_ALLOWED=1"
if /I "%MODE%"=="build-all" set "INSTALL_ALLOWED=1"
if /I "%MODE%"=="verify" set "INSTALL_ALLOWED=0"

if /I not "%MODE%"=="setup" if /I not "%MODE%"=="verify" if /I not "%MODE%"=="build-win" if /I not "%MODE%"=="build-apk" if /I not "%MODE%"=="build-aab" if /I not "%MODE%"=="build-all" goto :usage

set "FAILED=0"
set "MANUAL_ANDROID_STEPS=0"
set "WINGET_AVAILABLE=0"

call :check_winget
call :ensure_node
call :ensure_git
call :ensure_vscode
call :ensure_android_studio
call :ensure_project_dependencies
call :ensure_runtime
call :ensure_android_sdk
call :verify_release_signing

if "%FAILED%"=="1" goto :finish

if /I "%MODE%"=="verify" goto :verify
if /I "%MODE%"=="setup" goto :verify
if /I "%MODE%"=="build-win" goto :build_win
if /I "%MODE%"=="build-apk" goto :build_apk
if /I "%MODE%"=="build-aab" goto :build_aab
if /I "%MODE%"=="build-all" goto :build_all

goto :finish

:usage
echo Usage: setup-and-build.bat [setup^|verify^|build-win^|build-apk^|build-aab^|build-all]
echo.
echo   setup      Verify tools, install missing desktop prerequisites, install npm deps, bootstrap runtime
echo   verify     Report current prerequisite status without installing anything
echo   build-win  Run setup then build the Windows Electron package
echo   build-apk  Run setup then build the Android release APK
echo   build-aab  Run setup then build the Android release AAB
echo   build-all  Run setup then build Windows, APK, and AAB artifacts
exit /b 1

:check_winget
where winget >nul 2>nul
if errorlevel 1 (
  if "%INSTALL_ALLOWED%"=="1" (
    echo [missing] winget is required to auto-install prerequisites.
    set "FAILED=1"
  ) else (
    echo [warn] winget not found. Verify mode will continue without install support.
  )
) else (
  set "WINGET_AVAILABLE=1"
  echo [ok] winget
)
exit /b 0

:ensure_node
where node >nul 2>nul
if errorlevel 1 (
  if "%INSTALL_ALLOWED%"=="1" (
    if "%WINGET_AVAILABLE%"=="1" (
      echo [install] Node.js LTS
      winget install -e --id OpenJS.NodeJS.LTS || set "FAILED=1"
    ) else (
      echo [missing] Node.js
      set "FAILED=1"
    )
  ) else (
    echo [missing] Node.js
    set "FAILED=1"
  )
) else (
  echo [ok] Node.js
)
exit /b 0

:ensure_git
where git >nul 2>nul
if errorlevel 1 (
  if exist "%ProgramFiles%\Git\cmd\git.exe" (
    echo [ok] Git
  ) else (
    if "%INSTALL_ALLOWED%"=="1" (
      if "%WINGET_AVAILABLE%"=="1" (
        echo [install] Git
        winget install -e --id Git.Git || set "FAILED=1"
      ) else (
        echo [missing] Git
        set "FAILED=1"
      )
    ) else (
      echo [missing] Git
      set "FAILED=1"
    )
  )
) else (
  echo [ok] Git
)
exit /b 0

:ensure_vscode
where code >nul 2>nul
if errorlevel 1 (
  if exist "%LocalAppData%\Programs\Microsoft VS Code\Code.exe" (
    echo [ok] VS Code
  ) else (
    if exist "%ProgramFiles%\Microsoft VS Code\Code.exe" (
      echo [ok] VS Code
    ) else (
      if "%INSTALL_ALLOWED%"=="1" (
        if "%WINGET_AVAILABLE%"=="1" (
          echo [install] Visual Studio Code
          winget install -e --id Microsoft.VisualStudioCode || set "FAILED=1"
        ) else (
          echo [missing] VS Code
          set "FAILED=1"
        )
      ) else (
        echo [missing] VS Code
        set "FAILED=1"
      )
    )
  )
) else (
  echo [ok] VS Code
)
exit /b 0

:ensure_android_studio
if exist "%ProgramFiles%\Android\Android Studio\bin\studio64.exe" (
  echo [ok] Android Studio
) else (
  if "%INSTALL_ALLOWED%"=="1" (
    if "%WINGET_AVAILABLE%"=="1" (
      echo [install] Android Studio
      winget install -e --id Google.AndroidStudio || set "FAILED=1"
    ) else (
      echo [missing] Android Studio
      set "FAILED=1"
    )
  ) else (
    echo [missing] Android Studio
    set "FAILED=1"
  )
)
exit /b 0

:ensure_project_dependencies
if not exist package.json (
  echo [missing] package.json was not found in %ROOT%
  set "FAILED=1"
  exit /b 0
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [missing] npm
  set "FAILED=1"
  exit /b 0
)

if "%INSTALL_ALLOWED%"=="1" (
  echo [run] npm install
  call npm install || set "FAILED=1"
) else (
  if exist node_modules (
    echo [ok] node_modules
  ) else (
    echo [missing] node_modules
    set "FAILED=1"
  )
)

call npm ls electron-builder --depth=0 >nul 2>nul
if errorlevel 1 (
  if "%INSTALL_ALLOWED%"=="1" (
    echo [install] electron-builder
    call npm install --save-dev electron-builder || set "FAILED=1"
  ) else (
    echo [missing] electron-builder
    set "FAILED=1"
  )
) else (
  echo [ok] electron-builder
)
exit /b 0

:ensure_runtime
if "%INSTALL_ALLOWED%"=="1" (
  echo [run] npm run bootstrap:runtime
  call npm run bootstrap:runtime || set "FAILED=1"
) else (
  if exist ".ult-runtime" (
    echo [ok] runtime bootstrap directory
  ) else (
    echo [warn] runtime bootstrap directory is missing
  )
)
exit /b 0

:ensure_android_sdk
set "ANDROID_SDK_DIR="
if defined ANDROID_HOME if exist "%ANDROID_HOME%" set "ANDROID_SDK_DIR=%ANDROID_HOME%"
if not defined ANDROID_SDK_DIR if exist "%LOCALAPPDATA%\Android\Sdk" set "ANDROID_SDK_DIR=%LOCALAPPDATA%\Android\Sdk"

if not defined ANDROID_SDK_DIR (
  echo [manual] Android SDK was not found.
  echo          Open Android Studio ^> SDK Manager and install Platform-Tools, Build-Tools, and Command-line Tools.
  set "MANUAL_ANDROID_STEPS=1"
  if /I not "%MODE%"=="setup" if /I not "%MODE%"=="verify" set "FAILED=1"
  exit /b 0
)

if exist "%ANDROID_SDK_DIR%\platform-tools\adb.exe" (
  echo [ok] Android SDK platform-tools
) else (
  echo [manual] Android SDK exists but platform-tools are missing.
  echo          Open Android Studio ^> SDK Manager and install Platform-Tools.
  set "MANUAL_ANDROID_STEPS=1"
  if /I not "%MODE%"=="setup" if /I not "%MODE%"=="verify" set "FAILED=1"
)

if "%INSTALL_ALLOWED%"=="1" if exist "%ROOT%tools\configure-android-env.ps1" (
  powershell -ExecutionPolicy Bypass -File "%ROOT%tools\configure-android-env.ps1" -SdkRoot "%ANDROID_SDK_DIR%" -Quiet >nul
)

set "ANDROID_HOME=%ANDROID_SDK_DIR%"
set "PATH=%ANDROID_SDK_DIR%\platform-tools;%ANDROID_SDK_DIR%\cmdline-tools\latest\bin;%PATH%"
exit /b 0

:verify_release_signing
if exist "apps\android\keystore.properties" (
  echo [ok] Android release signing config
  exit /b 0
)

if defined ULT_ANDROID_KEYSTORE if defined ULT_ANDROID_KEYSTORE_PASSWORD if defined ULT_ANDROID_KEY_ALIAS if defined ULT_ANDROID_KEY_PASSWORD (
  echo [ok] Android release signing env vars
  exit /b 0
)

echo [manual] Android release signing is not configured.
echo          Copy apps\android\keystore.properties.example to apps\android\keystore.properties
echo          or set ULT_ANDROID_KEYSTORE, ULT_ANDROID_KEYSTORE_PASSWORD, ULT_ANDROID_KEY_ALIAS, and ULT_ANDROID_KEY_PASSWORD.
if /I "%MODE%"=="build-apk" set "FAILED=1"
if /I "%MODE%"=="build-aab" set "FAILED=1"
if /I "%MODE%"=="build-all" set "FAILED=1"
exit /b 0

:verify
echo.
echo Verification commands:
echo   node -v
echo   git --version
echo   code --version
if defined ANDROID_SDK_DIR (
  echo   "%ANDROID_SDK_DIR%\platform-tools\adb.exe" version
) else (
  echo   adb version
)
echo   npx electron-builder --version
if "%MANUAL_ANDROID_STEPS%"=="1" (
  echo.
  echo Android setup still needs manual SDK Manager steps before mobile builds can run.
)
goto :finish

:build_win
echo [run] npm run package:windows
call npm run package:windows || set "FAILED=1"
goto :finish

:build_apk
echo [run] npm run android:apk
call npm run android:apk || set "FAILED=1"
goto :finish

:build_aab
echo [run] npm run android:aab
call npm run android:aab || set "FAILED=1"
goto :finish

:build_all
echo [run] npm run package:windows
call npm run package:windows || set "FAILED=1"
if "%FAILED%"=="1" goto :finish
echo [run] npm run android:apk
call npm run android:apk || set "FAILED=1"
if "%FAILED%"=="1" goto :finish
echo [run] npm run android:aab
call npm run android:aab || set "FAILED=1"
goto :finish

:finish
if "%FAILED%"=="1" (
  echo.
  echo Setup/build did not complete successfully.
  exit /b 1
)

echo.
echo Setup/build step completed.
exit /b 0
