$ErrorActionPreference = "SilentlyContinue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$runtime = Join-Path $root "runtime"
$logs = Join-Path $root "logs"
if (!(Test-Path $logs)) {
  New-Item -ItemType Directory -Path $logs | Out-Null
}
$shutdownLog = Join-Path $logs "shutdown.log"

function Write-ShutdownLog($message) {
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $shutdownLog -Value "[$stamp] $message"
}

function Stop-PidFile($path, $label) {
  if (!(Test-Path $path)) {
    return
  }
  $raw = (Get-Content -LiteralPath $path -ErrorAction SilentlyContinue | Select-Object -First 1)
  $pidValue = 0
  [void][int]::TryParse($raw, [ref]$pidValue)
  if ($pidValue -gt 0) {
    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($process) {
      Write-ShutdownLog "Stopping $label pid=$pidValue"
      Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
    }
  }
  Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
}

Write-ShutdownLog "Shutdown requested."

Stop-PidFile (Join-Path $runtime "backend.pid") "backend"

$backendConn = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($backendConn) {
  $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($backendConn.OwningProcess)" -ErrorAction SilentlyContinue
  if ($owner -and ($owner.CommandLine -like "*universal-ai*" -or $owner.CommandLine -like "*backend.main*" -or $owner.CommandLine -like "*backend\run_server.py*")) {
    Write-ShutdownLog "Stopping backend port owner pid=$($backendConn.OwningProcess)"
    Stop-Process -Id $backendConn.OwningProcess -Force -ErrorAction SilentlyContinue
  }
}

$devConn = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($devConn) {
  $owner = Get-CimInstance Win32_Process -Filter "ProcessId=$($devConn.OwningProcess)" -ErrorAction SilentlyContinue
  if ($owner -and ($owner.CommandLine -like "*apps\desktop*" -or $owner.CommandLine -like "*vite*")) {
    Write-ShutdownLog "Stopping dev UI port owner pid=$($devConn.OwningProcess)"
    Stop-Process -Id $devConn.OwningProcess -Force -ErrorAction SilentlyContinue
  }
}

$ollamaMarkers = @(
  (Join-Path $runtime "ollama-started-by-kattappa.flag"),
  (Join-Path $runtime "ollama-started-by-sekhar.flag")
)
if ($ollamaMarkers | Where-Object { Test-Path $_ }) {
  Stop-PidFile (Join-Path $runtime "ollama.pid") "ollama"
  $ollamaProcesses = Get-CimInstance Win32_Process -Filter "Name='ollama.exe'" -ErrorAction SilentlyContinue
  foreach ($process in $ollamaProcesses) {
    if ($process.CommandLine -like "*serve*") {
      Write-ShutdownLog "Stopping Kattappa-started Ollama serve pid=$($process.ProcessId)"
      Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
  }
  foreach ($marker in $ollamaMarkers) {
    Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue
  }
}

Write-ShutdownLog "Shutdown completed."
