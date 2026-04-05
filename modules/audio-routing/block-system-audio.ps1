# Block System Audio Output
# Mutes system audio to prevent original audio from playing

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class AudioControl {
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutSetVolume(IntPtr hwo, uint dwVolume);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutGetVolume(IntPtr hwo, out uint pdwVolume);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutGetNumDevs();

    // Master volume control (more reliable for system-wide muting)
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutSetVolume(IntPtr hwo, uint dwVolume);
}
"@

function Set-SystemAudioMute {
    param([bool]$Mute = $true)

    try {
        # Get number of output devices
        $deviceCount = [AudioControl]::waveOutGetNumDevs()

        if ($Mute) {
            # Mute all output devices
            for ($i = 0; $i -lt $deviceCount; $i++) {
                $deviceHandle = [IntPtr]($i - 1) # WAVE_MAPPER = -1
                [void][AudioControl]::waveOutSetVolume($deviceHandle, 0)
            }
            Write-Host "System audio muted"
        } else {
            # Restore volume (this is approximate - we'd need to store original volumes)
            for ($i = 0; $i -lt $deviceCount; $i++) {
                $deviceHandle = [IntPtr]($i - 1)
                [void][AudioControl]::waveOutSetVolume($deviceHandle, 0xFFFF) # Max volume
            }
            Write-Host "System audio unmuted"
        }
    } catch {
        Write-Error "Failed to control system audio: $_"
        exit 1
    }
}

# Mute system audio
Set-SystemAudioMute -Mute $true

# Keep process alive to maintain mute state
Write-Host "Audio blocking active. Press Ctrl+C to stop."

try {
    while ($true) {
        Start-Sleep -Seconds 1
    }
} finally {
    # Unmute when script exits
    Set-SystemAudioMute -Mute $false
}