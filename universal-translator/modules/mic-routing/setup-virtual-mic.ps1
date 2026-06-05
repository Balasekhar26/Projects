# Virtual Microphone Setup and Routing
# Configures system-level microphone interception via virtual devices

param(
    [Parameter(Mandatory=$false)]
    [string]$VirtualMicName = "VB-Audio Virtual Microphone",
    
    [Parameter(Mandatory=$false)]
    [string]$Action = "setup"  # setup, status, cleanup
)

$ErrorActionPreference = "Stop"

function Check-VirtualMicAvailable {
    param([string]$DeviceName)
    
    $adapters = Get-WmiObject -Class Win32_SoundDevice | Where-Object { $_.Name -like "*Virtual*" -or $_.Name -like "*CABLE*" }
    return $adapters | Where-Object { $_.Name -eq $DeviceName }
}

function Init-VirtualMicDriver {
    param([string]$DeviceName)
    
    $existingDevice = Check-VirtualMicAvailable -DeviceName $DeviceName
    if ($existingDevice) {
        Write-Host "[OK] Virtual microphone device already available: $DeviceName"
        return $true
    }
    
    Write-Host "[INFO] Virtual microphone not found. Install Voicemeeter Banana or VB-CABLE AUDIO"
    Write-Host "[INFO] VB-CABLE: https://vb-audio.com/Cable/"
    Write-Host "[INFO] Voicemeeter: https://vb-audio.com/Voicemeeter/"
    
    return $false
}

function Get-VirtualMicDeviceId {
    param([string]$DeviceName)
    
    try {
        # Get from Windows Registry
        $regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\MediaCategories"
        $devices = Get-ChildItem -Path $regPath -ErrorAction SilentlyContinue
        
        foreach ($device in $devices) {
            $name = (Get-ItemProperty -Path $device.PSPath -Name "(Default)" -ErrorAction SilentlyContinue)."(Default)"
            if ($name -eq $DeviceName) {
                return $device.PSChildName
            }
        }
    } catch {
        Write-Warning "Could not retrieve device ID from registry: $_"
    }
    
    return $null
}

function Setup-MicrophoneRouting {
    param(
        [string]$PhysicalMicName,
        [string]$VirtualMicName
    )
    
    Write-Host "[INFO] Setting up microphone routing..."
    Write-Host "  Physical microphone: $PhysicalMicName"
    Write-Host "  Virtual microphone: $VirtualMicName"
    
    $device = Check-VirtualMicAvailable -DeviceName $VirtualMicName
    if (-not $device) {
        Write-Error "Virtual microphone device not found. Please install VB-CABLE or Voicemeeter first."
        return $false
    }
    
    # Register virtual mic in registry for application discovery
    try {
        $regPath = "HKCU:\Software\ULT"
        if (-not (Test-Path $regPath)) {
            New-Item -Path $regPath -Force | Out-Null
        }
        
        $micPath = Join-Path $regPath "MicrophoneRouting"
        if (-not (Test-Path $micPath)) {
            New-Item -Path $micPath -Force | Out-Null
        }
        
        Set-ItemProperty -Path $micPath -Name "VirtualMicrophoneName" -Value $VirtualMicName -Force
        Set-ItemProperty -Path $micPath -Name "PhysicalMicrophoneName" -Value $PhysicalMicName -Force
        Set-ItemProperty -Path $micPath -Name "RoutingEnabled" -Value 1 -Force
        Set-ItemProperty -Path $micPath -Name "SetupTimestamp" -Value (Get-Date).ToString("o") -Force
        
        Write-Host "[OK] Microphone routing configuration saved to registry"
        return $true
    } catch {
        Write-Error "Failed to configure registry: $_"
        return $false
    }
}

function Get-RoutingStatus {
    try {
        $regPath = "HKCU:\Software\ULT\MicrophoneRouting"
        if (Test-Path $regPath) {
            $config = Get-ItemProperty -Path $regPath
            Write-Host "[STATUS] Microphone Routing Configuration:"
            Write-Host "  Virtual Device: $($config.VirtualMicrophoneName)"
            Write-Host "  Physical Device: $($config.PhysicalMicrophoneName)"
            Write-Host "  Enabled: $(if ($config.RoutingEnabled -eq 1) { 'Yes' } else { 'No' })"
            Write-Host "  Last Setup: $($config.SetupTimestamp)"
            return $true
        } else {
            Write-Host "[INFO] No microphone routing configured yet"
            return $false
        }
    } catch {
        Write-Error "Failed to retrieve routing status: $_"
        return $false
    }
}

function Cleanup-MicrophoneRouting {
    try {
        $regPath = "HKCU:\Software\ULT\MicrophoneRouting"
        if (Test-Path $regPath) {
            Remove-Item -Path $regPath -Force
            Write-Host "[OK] Microphone routing configuration removed"
            return $true
        }
    } catch {
        Write-Error "Failed to cleanup: $_"
        return $false
    }
}

# Main execution
switch ($Action.ToLower()) {
    "setup" {
        $physicalMic = "Microphone"
        if ((Init-VirtualMicDriver -DeviceName $VirtualMicName)) {
            Setup-MicrophoneRouting -PhysicalMicName $physicalMic -VirtualMicName $VirtualMicName
        }
    }
    "status" {
        Get-RoutingStatus
    }
    "cleanup" {
        Cleanup-MicrophoneRouting
    }
    default {
        Write-Error "Unknown action: $Action. Use 'setup', 'status', or 'cleanup'"
    }
}
