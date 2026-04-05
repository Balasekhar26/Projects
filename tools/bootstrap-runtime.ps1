param()

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $root ".ult-runtime"
$tempDir = Join-Path $runtimeDir "temp"
$voiceProfilesDir = Join-Path $root "models\\voice-profiles"
$argosDir = Join-Path $root "models\\argos"

foreach ($path in @($runtimeDir, $tempDir, $voiceProfilesDir, $argosDir)) {
  New-Item -ItemType Directory -Force -Path $path | Out-Null
}

Write-Output "ULT runtime directories are ready."
