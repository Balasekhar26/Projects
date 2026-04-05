@echo off
setlocal
set SCRIPT_DIR=%~dp0
set DIST_DIR=%SCRIPT_DIR%.gradle-wrapper
set ZIP_PATH=%DIST_DIR%\gradle-8.10.2-bin.zip
set GRADLE_HOME=%DIST_DIR%\gradle-8.10.2

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

if not exist "%GRADLE_HOME%\bin\gradle.bat" (
  echo Downloading Gradle 8.10.2...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri 'https://services.gradle.org/distributions/gradle-8.10.2-bin.zip' -OutFile '%ZIP_PATH%'; Expand-Archive -Force '%ZIP_PATH%' '%DIST_DIR%'"
)

call "%GRADLE_HOME%\bin\gradle.bat" %*
