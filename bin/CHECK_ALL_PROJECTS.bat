@echo off
setlocal
cd /d "%~dp0.."

echo Checking canonical project folders...
for %%D in (
  universal-ai
  pcb-doctor
  ai-cyber-shield
  universal-translator
  musical-keyboard
  dews
  07-NeuroSeed
) do (
  if exist "%%D\" (
    echo [OK] %%D
  ) else (
    echo [MISSING] %%D
  )
)

if exist "ult-translator\" (
  echo [STALE] ult-translator should not be used. Move source to universal-translator.
) else (
  echo [OK] No stale ult-translator folder.
)

endlocal
