@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0CHECK_PRODUCTION_READINESS.ps1" %*
exit /b %ERRORLEVEL%
