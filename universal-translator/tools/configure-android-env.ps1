param(
  [string]$SdkRoot,
  [switch]$Quiet
)

$ErrorActionPreference = "Stop"

function Resolve-AndroidSdkRoot {
  param([string]$Candidate)

  if ($Candidate -and (Test-Path $Candidate)) {
    return (Resolve-Path $Candidate).Path
  }

  if ($env:ANDROID_HOME -and (Test-Path $env:ANDROID_HOME)) {
    return (Resolve-Path $env:ANDROID_HOME).Path
  }

  $defaultSdkRoot = Join-Path $env:LOCALAPPDATA "Android\Sdk"
  if (Test-Path $defaultSdkRoot) {
    return (Resolve-Path $defaultSdkRoot).Path
  }

  throw "Android SDK root was not found. Install it from Android Studio SDK Manager first."
}

function Add-UserPathEntry {
  param([string]$PathEntry)

  if (-not (Test-Path $PathEntry)) {
    return $false
  }

  $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $segments = @()
  if ($currentUserPath) {
    $segments = $currentUserPath.Split(";", [System.StringSplitOptions]::RemoveEmptyEntries)
  }

  foreach ($segment in $segments) {
    if ($segment.TrimEnd("\") -ieq $PathEntry.TrimEnd("\")) {
      return $false
    }
  }

  $updatedPath = @($segments + $PathEntry) -join ";"
  [Environment]::SetEnvironmentVariable("Path", $updatedPath, "User")
  return $true
}

$resolvedSdkRoot = Resolve-AndroidSdkRoot -Candidate $SdkRoot
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $resolvedSdkRoot, "User")
$env:ANDROID_HOME = $resolvedSdkRoot

$pathUpdates = @()

$platformTools = Join-Path $resolvedSdkRoot "platform-tools"
if (Add-UserPathEntry -PathEntry $platformTools) {
  $pathUpdates += $platformTools
}

$cmdlineTools = Join-Path $resolvedSdkRoot "cmdline-tools\latest\bin"
if (Add-UserPathEntry -PathEntry $cmdlineTools) {
  $pathUpdates += $cmdlineTools
}

if (-not $Quiet) {
  Write-Output "ANDROID_HOME configured at $resolvedSdkRoot"
  if ($pathUpdates.Count -gt 0) {
    Write-Output "Added PATH entries:"
    foreach ($entry in $pathUpdates) {
      Write-Output " - $entry"
    }
  } else {
    Write-Output "PATH entries already configured."
  }
}
