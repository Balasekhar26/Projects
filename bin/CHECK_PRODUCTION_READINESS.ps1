param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$Failures = New-Object System.Collections.Generic.List[string]

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host "== $Title =="
}

function Add-Failure {
    param([string]$Name, [string]$Message)
    $Failures.Add("$Name :: $Message") | Out-Null
    Write-Host "[FAIL] $Name - $Message" -ForegroundColor Red
}

function Pass {
    param([string]$Name)
    Write-Host "[OK] $Name" -ForegroundColor Green
}

function Check-Path {
    param([string]$Name, [string]$Path)
    if (Test-Path -LiteralPath (Join-Path $Root $Path)) {
        Pass $Name
    } else {
        Add-Failure $Name "Missing $Path"
    }
}

function Run-Command {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [scriptblock]$Command
    )

    Write-Host "[RUN] $Name"
    Push-Location (Join-Path $Root $WorkingDirectory)
    try {
        & $Command
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
            Add-Failure $Name "Exit code $LASTEXITCODE"
        } else {
            Pass $Name
        }
    } catch {
        Add-Failure $Name $_.Exception.Message
    } finally {
        Pop-Location
    }
}

Write-Section "Canonical Project Layout"
$Projects = @(
    "universal-ai",
    "pcb-doctor",
    "ai-cyber-shield",
    "universal-translator",
    "musical-keyboard",
    "dews",
    "07-NeuroSeed"
)
foreach ($Project in $Projects) {
    Check-Path $Project $Project
}

if (Test-Path (Join-Path $Root "ult-translator")) {
    Add-Failure "canonical translator path" "Stale ult-translator folder exists"
} else {
    Pass "canonical translator path"
}

if (Test-Path (Join-Path $Root "universal-translator\.git")) {
    Add-Failure "translator nested git" "universal-translator still contains nested .git"
} else {
    Pass "translator nested git"
}

Write-Section "Required Production Files"
Check-Path "workspace readme" "bin\WORKSPACE_README.md"
Check-Path "project index" "bin\PROJECTS_INDEX.md"
Check-Path "root gitignore copy" "bin\root.gitignore"
foreach ($Project in $Projects) {
    Check-Path "$Project setup" "$Project\setup.bat"
    Check-Path "$Project run executable" "$Project\run.exe"
    $extraRootLaunchers = Get-ChildItem -LiteralPath (Join-Path $Root $Project) -File |
        Where-Object {
            ($_.Extension -in @(".bat", ".ps1", ".exe")) -and
            ($_.Name -notin @("setup.bat", "run.exe"))
        }
    if ($extraRootLaunchers) {
        Add-Failure "$Project root launchers" (
            "Only setup.bat and run.exe are allowed at project root; found " +
            (($extraRootLaunchers | Select-Object -ExpandProperty Name) -join ", ")
        )
    } else {
        Pass "$Project root launchers"
    }
}
Check-Path "translator env example" "universal-translator\.env.example"
Check-Path "universal ai env example" "universal-ai\.env.example"
Check-Path "cyber shield env example" "ai-cyber-shield\.env.example"
Check-Path "neuroseed prototype" "07-NeuroSeed\prototype\index.html"

Write-Section "Local-First and Safety Boundaries"
$NeuroSeedIndex = Join-Path $Root "07-NeuroSeed\prototype\index.html"
if ((Get-Content -LiteralPath $NeuroSeedIndex -Raw) -match "https?://") {
    Add-Failure "neuroseed offline prototype" "Prototype HTML references network assets"
} else {
    Pass "neuroseed offline prototype"
}

$DewsSource = Get-ChildItem -LiteralPath (Join-Path $Root "dews") -Recurse -File |
    Where-Object { $_.FullName -notmatch "\\node_modules\\" -and $_.Extension -in ".py",".md",".tsx",".ts",".js",".json" }
$UnsafeDews = $DewsSource | Select-String -Pattern "weapon destroyer|ammunition disabling|directed energy weapon|heat the primer" -SimpleMatch
if ($UnsafeDews) {
    Add-Failure "dews safe-domain source" "Unsafe DEWS wording found in implementation files"
} else {
    Pass "dews safe-domain source"
}

Write-Section "Source and Test Checks"
Run-Command "universal-translator tests" "universal-translator" { npm test }
Run-Command "universal-translator typecheck" "universal-translator" { npm run typecheck }
Run-Command "musical-keyboard typecheck" "musical-keyboard" { npm run typecheck }
Run-Command "pcb-doctor unittest" "pcb-doctor" {
    $env:PYTHONPATH = (Get-Location).Path
    python -m unittest discover tests
}
Run-Command "ai-cyber-shield unittest" "ai-cyber-shield" {
    $env:PYTHONPATH = (Get-Location).Path
    python -m unittest discover tests
}
Run-Command "dews unittest" "dews" {
    $env:PYTHONPATH = (Get-Location).Path
    python -m unittest discover tests
}
Run-Command "universal-ai core compile" "universal-ai" {
    python -m py_compile backend\core\memory.py backend\core\safety.py
}

if ($Full) {
    Write-Section "Full Build Checks"
    Run-Command "musical-keyboard build" "musical-keyboard" { npm run build }
    Run-Command "dews dashboard build" "dews" { npm run build }
    Run-Command "pcb-doctor dashboard build" "pcb-doctor" { npm run build }
    Run-Command "ai-cyber-shield dashboard build" "ai-cyber-shield" { npm run build }
}

Write-Section "Git Hygiene"
$Generated = git -C $Root diff --cached --name-only --diff-filter=A |
    Where-Object {
        ($_ -match '(^|/)(node_modules|__pycache__|dist|build|coverage|\.tmp|share|sox-14\.4\.2)(/|$)') -or
        ($_ -cmatch '(^|/)(Scripts|Lib)(/|$)') -or
        ($_ -match '\.(wav|db|sqlite|pyc)$') -or
        ($_ -match '\.exe$' -and $_ -notmatch '^(universal-ai|pcb-doctor|ai-cyber-shield|universal-translator|musical-keyboard|dews|07-NeuroSeed)/run\.exe$') -or
        ($_ -match '(^|/)runtime/' -and $_ -notmatch '\.gitkeep$')
    }
if ($Generated) {
    Add-Failure "staged generated files" ($Generated -join ", ")
} else {
    Pass "staged generated files"
}

Write-Section "Result"
if ($Failures.Count -gt 0) {
    Write-Host "Production readiness check failed:" -ForegroundColor Red
    $Failures | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "All production readiness checks passed." -ForegroundColor Green
exit 0
