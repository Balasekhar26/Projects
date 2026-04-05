# Play Audio on Specific Device
# Routes translated audio to target output device

param(
    [Parameter(Mandatory=$true)]
    [string]$Device,

    [Parameter(Mandatory=$true)]
    [string]$Data  # Base64 encoded PCM data
)

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.IO;

public class AudioPlayback {
    [StructLayout(LayoutKind.Sequential)]
    public struct WAVEFORMATEX {
        public ushort wFormatTag;
        public ushort nChannels;
        public uint nSamplesPerSec;
        public uint nAvgBytesPerSec;
        public ushort nBlockAlign;
        public ushort wBitsPerSample;
        public ushort cbSize;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct WAVEOUTCAPS {
        public ushort wMid;
        public ushort wPid;
        public uint vDriverVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string szPname;
        public uint dwFormats;
        public ushort wChannels;
        public ushort wReserved1;
        public uint dwSupport;
    }

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutOpen(out IntPtr phwo, IntPtr uDeviceID, ref WAVEFORMATEX pwfx, IntPtr dwCallback, IntPtr dwInstance, uint fdwOpen);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutWrite(IntPtr hwo, IntPtr pwh, uint cbwh);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutClose(IntPtr hwo);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutPrepareHeader(IntPtr hwo, IntPtr pwh, uint cbwh);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutUnprepareHeader(IntPtr hwo, IntPtr pwh, uint cbwh);

    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern uint waveOutGetDevCaps(IntPtr uDeviceID, out WAVEOUTCAPS pwoc, uint cbwoc);

    [StructLayout(LayoutKind.Sequential)]
    public struct WAVEHDR {
        public IntPtr lpData;
        public uint dwBufferLength;
        public uint dwBytesRecorded;
        public IntPtr dwUser;
        public uint dwFlags;
        public uint dwLoops;
        public IntPtr lpNext;
        public IntPtr reserved;
    }

    public const uint WAVE_MAPPER = 0xFFFFFFFF;
    public const uint CALLBACK_NULL = 0x00000000;
    public const uint WAVE_FORMAT_PCM = 1;
    public const uint WHDR_DONE = 0x00000001;
    public const uint WHDR_PREPARED = 0x00000002;
    public const uint WHDR_BEGINLOOP = 0x00000004;
    public const uint WHDR_ENDLOOP = 0x00000008;
    public const uint WHDR_INQUEUE = 0x00000010;

    public const uint MMSYSERR_NOERROR = 0;
}
"@

function Play-PcmAudio {
    param(
        [string]$DeviceName,
        [byte[]]$PcmData
    )

    try {
        # Find device by name
        $deviceId = [IntPtr]::Zero
        $deviceCount = 0

        # Get device count
        Add-Type -TypeDefinition @"
        using System.Runtime.InteropServices;
        public class WaveDev { [DllImport("winmm.dll")] public static extern uint waveOutGetNumDevs(); }
"@
        $deviceCount = [WaveDev]::waveOutGetNumDevs()

        # Find matching device
        for ($i = 0; $i -lt $deviceCount; $i++) {
            $caps = New-Object AudioPlayback+WAVEOUTCAPS
            $result = [AudioPlayback]::waveOutGetDevCaps([IntPtr]$i, [ref]$caps, [uint32][Runtime.InteropServices.Marshal]::SizeOf([type]'AudioPlayback+WAVEOUTCAPS'))

            if ($result -eq 0 -and $caps.szPname.Trim() -eq $DeviceName) {
                $deviceId = [IntPtr]$i
                break
            }
        }

        if ($deviceId -eq [IntPtr]::Zero) {
            Write-Error "Device '$DeviceName' not found"
            return
        }

        # Set up wave format (16-bit PCM, 16kHz, mono)
        $waveFormat = New-Object AudioPlayback+WAVEFORMATEX
        $waveFormat.wFormatTag = [AudioPlayback]::WAVE_FORMAT_PCM
        $waveFormat.nChannels = 1
        $waveFormat.nSamplesPerSec = 16000
        $waveFormat.wBitsPerSample = 16
        $waveFormat.nBlockAlign = [uint16]($waveFormat.wBitsPerSample / 8 * $waveFormat.nChannels)
        $waveFormat.nAvgBytesPerSec = $waveFormat.nSamplesPerSec * $waveFormat.nBlockAlign
        $waveFormat.cbSize = 0

        # Open audio device
        $hWaveOut = [IntPtr]::Zero
        $result = [AudioPlayback]::waveOutOpen([ref]$hWaveOut, $deviceId, [ref]$waveFormat, [IntPtr]::Zero, [IntPtr]::Zero, [AudioPlayback]::CALLBACK_NULL)

        if ($result -ne [AudioPlayback]::MMSYSERR_NOERROR) {
            Write-Error "Failed to open audio device: $result"
            return
        }

        # Prepare wave header
        $waveHeader = New-Object AudioPlayback+WAVEHDR
        $dataPtr = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($PcmData.Length)
        [System.Runtime.InteropServices.Marshal]::Copy($PcmData, 0, $dataPtr, $PcmData.Length)

        $waveHeader.lpData = $dataPtr
        $waveHeader.dwBufferLength = [uint32]$PcmData.Length
        $waveHeader.dwFlags = 0
        $waveHeader.dwLoops = 0

        $headerPtr = [System.Runtime.InteropServices.Marshal]::AllocHglobal([System.Runtime.InteropServices.Marshal]::SizeOf([type]'AudioPlayback+WAVEHDR'))
        [System.Runtime.InteropServices.Marshal]::StructureToPtr($waveHeader, $headerPtr, $false)

        # Prepare header
        $result = [AudioPlayback]::waveOutPrepareHeader($hWaveOut, $headerPtr, [uint32][System.Runtime.InteropServices.Marshal]::SizeOf([type]'AudioPlayback+WAVEHDR'))
        if ($result -ne [AudioPlayback]::MMSYSERR_NOERROR) {
            Write-Error "Failed to prepare header: $result"
            [System.Runtime.InteropServices.Marshal]::FreeHGlobal($dataPtr)
            [System.Runtime.InteropServices.Marshal]::FreeHGlobal($headerPtr)
            [AudioPlayback]::waveOutClose($hWaveOut)
            return
        }

        # Play audio
        $result = [AudioPlayback]::waveOutWrite($hWaveOut, $headerPtr, [uint32][System.Runtime.InteropServices.Marshal]::SizeOf([type]'AudioPlayback+WAVEHDR'))
        if ($result -ne [AudioPlayback]::MMSYSERR_NOERROR) {
            Write-Error "Failed to write audio: $result"
        } else {
            # Wait for playback to complete
            $maxWait = 100 # 10 seconds max
            $waitCount = 0

            while ($waitCount -lt $maxWait) {
                $currentHeader = [System.Runtime.InteropServices.Marshal]::PtrToStructure($headerPtr, [type]'AudioPlayback+WAVEHDR')
                if (($currentHeader.dwFlags -band [AudioPlayback]::WHDR_DONE) -ne 0) {
                    break
                }
                Start-Sleep -Milliseconds 100
                $waitCount++
            }
        }

        # Cleanup
        [AudioPlayback]::waveOutUnprepareHeader($hWaveOut, $headerPtr, [uint32][System.Runtime.InteropServices.Marshal]::SizeOf([type]'AudioPlayback+WAVEHDR'))
        [AudioPlayback]::waveOutClose($hWaveOut)
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($dataPtr)
        [System.Runtime.InteropServices.Marshal]::FreeHGlobal($headerPtr)

    } catch {
        Write-Error "Audio playback failed: $_"
    }
}

# Decode base64 data and play
try {
    $pcmData = [Convert]::FromBase64String($Data)
    Play-PcmAudio -DeviceName $Device -PcmData $pcmData
} catch {
    Write-Error "Failed to decode audio data: $_"
    exit 1
}