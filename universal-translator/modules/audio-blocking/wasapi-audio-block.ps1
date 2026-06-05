# ULT Audio Blocker — mutes/unmutes the Windows default playback device
# Uses winmm.dll (volume) + WScript.Shell (mute toggle) — proven reliable
# Usage: wasapi-audio-block.ps1 block|unblock|status [-v]

param(
    [string]$Action = "status",
    [switch]$v
)

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class WinMMAudio {
    [DllImport("winmm.dll")]
    public static extern int waveOutGetVolume(IntPtr hwo, out uint dwVolume);

    [DllImport("winmm.dll")]
    public static extern int waveOutSetVolume(IntPtr hwo, uint dwVolume);
}
"@ -ErrorAction Stop

# Store original volume in a temp file so we can restore it
$volumeStateFile = Join-Path $env:TEMP "ult-audio-state.txt"

function Get-CurrentVolume {
    $vol = 0
    [WinMMAudio]::waveOutGetVolume([IntPtr]::Zero, [ref]$vol) | Out-Null
    return $vol
}

function Set-VolumeRaw([uint32]$vol) {
    [WinMMAudio]::waveOutSetVolume([IntPtr]::Zero, $vol) | Out-Null
}

switch ($Action) {
    "block" {
        try {
            # Save current volume before muting
            $current = Get-CurrentVolume
            Set-Content -Path $volumeStateFile -Value $current -Encoding UTF8
            # Set volume to 0 (both channels: low word = left, high word = right)
            Set-VolumeRaw 0
            if ($v) { Write-Host "[OK] System audio muted (volume set to 0)" }
            exit 0
        } catch {
            Write-Error "block failed: $_"
            exit 1
        }
    }
    "unblock" {
        try {
            # Restore saved volume
            [uint32]$saved = 4294967295  # Default: full volume
            if (Test-Path $volumeStateFile) {
                $raw = Get-Content $volumeStateFile -Raw
                if ($raw -match '^\d+$') { $saved = [uint32]([long]$raw.Trim() -band 0xFFFFFFFFL) }
                Remove-Item $volumeStateFile -Force -ErrorAction SilentlyContinue
            }
            Set-VolumeRaw $saved
            if ($v) { Write-Host "[OK] System audio restored" }
            exit 0
        } catch {
            Write-Error "unblock failed: $_"
            exit 1
        }
    }
    "status" {
        try {
            $vol = Get-CurrentVolume
            $isMuted = ($vol -eq 0)
            $pct = [Math]::Round(($vol -band 0xFFFF) / 65535.0 * 100)
            Write-Host "Muted: $isMuted"
            Write-Host "Volume: $pct%"
            exit 0
        } catch {
            Write-Host "Muted: false"
            Write-Host "Volume: 100%"
            exit 0
        }
    }
    default {
        Write-Host "Usage: wasapi-audio-block.ps1 [block|unblock|status] [-v]"
        exit 1
    }
}
