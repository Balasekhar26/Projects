# Advanced Audio Blocking via WASAPI
# Provides system-level audio blocking for speaker interception

Add-Type -AssemblyName System.Runtime.InteropServices

# Define WASAPI interfaces and constants
$AudioClientDef = @"
using System;
using System.Runtime.InteropServices;

[Guid("1CB9C6D8-FE41-4d8d-A280-27072A8CCD7F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDevice {
    [PreserveSig] int Activate([In] ref Guid iid, [In] uint dwClsCtx, [In] IntPtr pActivationParams, [Out] out IntPtr ppInterface);
    [PreserveSig] int OpenPropertyStore([In] uint stgmAccess, [Out] out IntPtr ppProperties);
    [PreserveSig] int GetId([Out] out string ppstrId);
    [PreserveSig] int GetState([Out] out uint pdwState);
}

[Guid("A95664D2-9614-4F23-8555-E2BD884C6FB7"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IMMDeviceEnumerator {
    [PreserveSig] int EnumAudioEndpoints([In] uint dataFlow, [In] uint dwStateMask, [Out] out IntPtr ppDevices);
    [PreserveSig] int GetDefaultAudioEndpoint([In] uint dataFlow, [In] uint role, [Out] out IMMDevice ppEndpoint);
    [PreserveSig] int GetDevice([In] string id, [Out] out IMMDevice ppDevice);
    [PreserveSig] int RegisterEndpointNotificationCallback([In] IntPtr pClient);
    [PreserveSig] int UnregisterEndpointNotificationCallback([In] IntPtr pClient);
}

[Guid("3B0D0EA4-D21A-4691-8D2D-18E048DB6807"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IAudioClient {
    [PreserveSig] int Initialize([In] uint shareMode, [In] uint streamFlags, [In] long hnsBufferDuration, [In] long hnsPeriodicity, [In] IntPtr pFormat, [In] IntPtr audioSessionGuid);
    [PreserveSig] int GetBufferSize([Out] out uint pNumBufferFrames);
    [PreserveSig] int GetStreamLatency([Out] out long phnsLatency);
    [PreserveSig] int GetCurrentPadding([Out] out uint pNumPaddingFrames);
    [PreserveSig] int IsFormatSupported([In] uint shareMode, [In] IntPtr pFormat, [Out] out IntPtr ppClosestMatch);
    [PreserveSig] int GetMixFormat([Out] out IntPtr ppDeviceFormat);
    [PreserveSig] int GetDevicePeriod([Out] out long phnsDefaultDevicePeriod, [Out] out long phnsMinimumDevicePeriod);
    [PreserveSig] int Start();
    [PreserveSig] int Stop();
    [PreserveSig] int Reset();
    [PreserveSig] int GetService([In] ref Guid riid, [Out] out IntPtr ppv);
}

[Guid("5CDF2C82-841E-4546-FD6D-3B375D6DEB24"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IAudioEndpointVolume {
    [PreserveSig] int RegisterControlChangeNotify([In] IntPtr pNotify);
    [PreserveSig] int UnregisterControlChangeNotify([In] IntPtr pNotify);
    [PreserveSig] int GetChannelCount([Out] out uint pnChannel);
    [PreserveSig] int SetMasterVolumeLevel([In] float fLevelDB, [In] ref Guid pguidEventContext);
    [PreserveSig] int SetMasterVolumeLevelScalar([In] float fLevel, [In] ref Guid pguidEventContext);
    [PreserveSig] int GetMasterVolumeLevel([Out] out float pfLevelDB);
    [PreserveSig] int GetMasterVolumeLevelScalar([Out] out float pfLevel);
    [PreserveSig] int SetChannelVolumeLevel([In] uint nChannel, [In] float fLevelDB, [In] ref Guid pguidEventContext);
    [PreserveSig] int SetChannelVolumeLevelScalar([In] uint nChannel, [In] float fLevel, [In] ref Guid pguidEventContext);
    [PreserveSig] int GetChannelVolumeLevel([In] uint nChannel, [Out] out float pfLevelDB);
    [PreserveSig] int GetChannelVolumeLevelScalar([In] uint nChannel, [Out] out float pfLevel);
    [PreserveSig] int SetMute([In] bool bMute, [In] ref Guid pguidEventContext);
    [PreserveSig] int GetMute([Out] out bool pbMute);
    [PreserveSig] int GetVolumeRange([Out] out float pfLevelMinDB, [Out] out float pfLevelMaxDB, [Out] out float pfVolumeIncrementDB);
    [PreserveSig] int QueryHardwareSupport([Out] out uint pdwHardwareSupportMask);
    [PreserveSig] int GetVolumeStatus([Out] out uint pStatus);
}

[GuidAttribute("D666063F-1587-4E43-81F1-B948E807363F")]
public class MMDeviceEnumerator { }
"@

Add-Type -TypeDefinition $AudioClientDef

function Block-SystemAudio {
    param(
        [bool]$Block = $true,
        [bool]$Verbose = $false
    )

    try {
        # Create device enumerator
        $enumerator = New-Object -ComObject MMDeviceEnumerator
        $defaultDevice = $enumerator.GetDefaultAudioEndpoint(0, 1)  # 0=eRender, 1=eConsole
        
        if ($null -eq $defaultDevice) {
            Write-Error "Failed to get default audio device"
            return $false
        }

        # Get audio endpoint volume control
        $iid = [Guid]"5CDF2C82-841E-4546-FD6D-3B375D6DEB24"
        $volumePtr = [IntPtr]::Zero
        $result = $defaultDevice.Activate([ref]$iid, 0, [IntPtr]::Zero, [ref]$volumePtr)

        if ($result -ne 0) {
            Write-Error "Failed to activate audio endpoint volume: $result"
            return $false
        }

        $volume = [Runtime.InteropServices.Marshal]::GetObjectForIUnknown($volumePtr)
        
        # Get current mute state
        $muteStatus = $false
        $volume.GetMute([ref]$muteStatus)
        
        $eventGuid = [Guid]::NewGuid()
        
        if ($Block) {
            if (-not $muteStatus) {
                $volume.SetMute($true, [ref]$eventGuid)
                if ($Verbose) { Write-Host "[OK] System audio muted" }
            } else {
                if ($Verbose) { Write-Host "[INFO] System audio already muted" }
            }
        } else {
            if ($muteStatus) {
                $volume.SetMute($false, [ref]$eventGuid)
                if ($Verbose) { Write-Host "[OK] System audio unmuted" }
            } else {
                if ($Verbose) { Write-Host "[INFO] System audio already unmuted" }
            }
        }

        # Cleanup COM object
        [Runtime.InteropServices.Marshal]::ReleaseComObject($volume) | Out-Null
        [Runtime.InteropServices.Marshal]::ReleaseComObject($defaultDevice) | Out-Null
        [Runtime.InteropServices.Marshal]::ReleaseComObject($enumerator) | Out-Null

        return $true
    } catch {
        Write-Error "Audio blocking failed: $_"
        return $false
    }
}

function Get-AudioMuteStatus {
    try {
        $enumerator = New-Object -ComObject MMDeviceEnumerator
        $defaultDevice = $enumerator.GetDefaultAudioEndpoint(0, 1)
        
        if ($null -eq $defaultDevice) {
            return $null
        }

        $iid = [Guid]"5CDF2C82-841E-4546-FD6D-3B375D6DEB24"
        $volumePtr = [IntPtr]::Zero
        $result = $defaultDevice.Activate([ref]$iid, 0, [IntPtr]::Zero, [ref]$volumePtr)

        if ($result -ne 0) {
            return $null
        }

        $volume = [Runtime.InteropServices.Marshal]::GetObjectForIUnknown($volumePtr)
        $muteStatus = $false
        $volume.GetMute([ref]$muteStatus)
        $level = 0.0
        $volume.GetMasterVolumeLevelScalar([ref]$level)

        [Runtime.InteropServices.Marshal]::ReleaseComObject($volume) | Out-Null
        [Runtime.InteropServices.Marshal]::ReleaseComObject($defaultDevice) | Out-Null
        [Runtime.InteropServices.Marshal]::ReleaseComObject($enumerator) | Out-Null

        return @{
            Muted = $muteStatus
            VolumeLevel = $level
        }
    } catch {
        return $null
    }
}

# Main execution
$action = $args[0]
$verbose = $args.Count -gt 1 -and $args[1] -eq "-v"

switch ($action) {
    "block" {
        if (Block-SystemAudio -Block $true -Verbose $verbose) {
            exit 0
        } else {
            exit 1
        }
    }
    "unblock" {
        if (Block-SystemAudio -Block $false -Verbose $verbose) {
            exit 0
        } else {
            exit 1
        }
    }
    "status" {
        $status = Get-AudioMuteStatus
        if ($status) {
            Write-Host "Muted: $($status.Muted)"
            Write-Host "Volume: $([Math]::Round($status.VolumeLevel * 100))%"
            exit 0
        } else {
            Write-Host "Failed to get audio status"
            exit 1
        }
    }
    default {
        Write-Host "Usage: $($MyInvocation.MyCommand.Name) [block|unblock|status] [-v]"
        exit 1
    }
}
