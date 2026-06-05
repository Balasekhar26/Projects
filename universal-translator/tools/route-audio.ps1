# route-audio.ps1 — Set/restore Windows default playback device
# intercept: routes all audio into CABLE Input (silent virtual sink) — original audio blocked
# restore:   restores the real speaker
# status:    shows current default playback device name

param([string]$Action = 'status')

$ErrorActionPreference = 'Stop'
$RegPath  = 'HKCU:\Software\ULT\AudioRouting'
$CsFile   = Join-Path $PSScriptRoot 'AudioRouter.cs'

if (-not ([System.Management.Automation.PSTypeName]'UltAudio.AudioRouter').Type) {
    Add-Type -Path $CsFile
}

function Get-FriendlyName {
    param([string]$id)
    try {
        $guid = ($id -split '\.')[-1]
        $p = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render\$guid\Properties"
        if (Test-Path $p) {
            $props = Get-ItemProperty $p -ErrorAction SilentlyContinue
            $v = $props.PSObject.Properties |
                 Where-Object { $_.Value -is [string] -and $_.Value.Length -gt 1 -and $_.Name -match '14\}' } |
                 Select-Object -First 1
            if ($v) { return $v.Value }
        }
    } catch {}
    return $id
}

function Find-DeviceIdByName {
    param([string]$pattern)
    $regBase = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render'
    $allIds  = [UltAudio.AudioRouter]::GetAllIds()
    $result  = $null
    Get-ChildItem $regBase -ErrorAction SilentlyContinue | ForEach-Object {
        if ($result) { return }
        $propPath = "$($_.PSPath)\Properties"
        if (Test-Path $propPath) {
            $props = Get-ItemProperty $propPath -ErrorAction SilentlyContinue
            $hit = $props.PSObject.Properties |
                   Where-Object { $_.Value -is [string] -and $_.Value -match $pattern } |
                   Select-Object -First 1
            if ($hit) {
                $guid   = $_.PSChildName
                $result = $allIds | Where-Object { $_ -match [regex]::Escape($guid) } | Select-Object -First 1
                if (-not $result) { $result = $guid }
            }
        }
    }
    return $result
}

switch ($Action.ToLower()) {

    'status' {
        $id   = [UltAudio.AudioRouter]::GetDefaultId()
        $name = Get-FriendlyName $id
        Write-Output "Default playback: $name"
        exit 0
    }

    'intercept' {
        $currentId   = [UltAudio.AudioRouter]::GetDefaultId()
        $currentName = Get-FriendlyName $currentId
        if (-not (Test-Path $RegPath)) { New-Item -Path $RegPath -Force | Out-Null }
        Set-ItemProperty -Path $RegPath -Name 'OriginalDeviceId' -Value $currentId -Force

        $cableId = Find-DeviceIdByName 'CABLE Input'
        if (-not $cableId) {
            Write-Output 'CABLE Input not found. Install VB-Audio CABLE: https://vb-audio.com/Cable/'
            exit 1
        }
        [UltAudio.AudioRouter]::SetDefault($cableId)
        Write-Output "Intercept ON. Original audio blocked. Saved: $currentName"
        exit 0
    }

    'restore' {
        if (-not (Test-Path $RegPath)) { Write-Output 'Nothing to restore.'; exit 0 }
        $savedId = (Get-ItemProperty $RegPath -Name 'OriginalDeviceId' -ErrorAction SilentlyContinue).OriginalDeviceId
        if (-not $savedId) { Write-Output 'No saved device.'; exit 0 }
        [UltAudio.AudioRouter]::SetDefault($savedId)
        $name = Get-FriendlyName $savedId
        Write-Output "Restored: $name"
        exit 0
    }

    default {
        Write-Error 'Usage: route-audio.ps1 [intercept|restore|status]'
        exit 1
    }
}
