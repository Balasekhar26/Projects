Set-Location $PSScriptRoot

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
  & $python.Source tests_smoke.py
  exit $LASTEXITCODE
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
  & $py.Source -3 tests_smoke.py
  exit $LASTEXITCODE
}

Write-Error "Python was not found. Install Python 3.10+ and rerun this script."
exit 1
