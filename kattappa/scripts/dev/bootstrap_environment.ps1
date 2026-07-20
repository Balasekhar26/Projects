param(
    [string]$PythonLauncher = "py",
    [string[]]$PythonArguments = @("-3.13"),
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Environment = Join-Path $RepoRoot "ai_system_env"

if ($Recreate -and (Test-Path -LiteralPath $Environment)) {
    $ResolvedEnvironment = (Resolve-Path -LiteralPath $Environment).Path
    if (-not $ResolvedEnvironment.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove environment outside repository: $ResolvedEnvironment"
    }
    Remove-Item -LiteralPath $ResolvedEnvironment -Recurse -Force
}

if (-not (Test-Path -LiteralPath (Join-Path $Environment "Scripts\python.exe"))) {
    & $PythonLauncher @PythonArguments -m venv $Environment
    if ($LASTEXITCODE -ne 0) { throw "Failed to create virtual environment" }
}

$PythonExe = Join-Path $Environment "Scripts\python.exe"
& $PythonExe -m pip install --requirement (Join-Path $RepoRoot "requirements.lock.txt")
if ($LASTEXITCODE -ne 0) { throw "Pinned dependency installation failed" }

Push-Location $RepoRoot
try {
    & $PythonExe scripts/dev/verify_environment.py
    if ($LASTEXITCODE -ne 0) { throw "Import provenance verification failed" }
    & $PythonExe -m pytest --collect-only -q
    if ($LASTEXITCODE -ne 0) { throw "Test collection failed" }
} finally {
    Pop-Location
}
