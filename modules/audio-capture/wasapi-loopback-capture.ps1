# WASAPI Loopback Capture Script
# Captures audio being sent to speakers before playback

param(
    [string]$DeviceId = $null  # Optional specific device ID
)

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Threading;

public class WasapiLoopbackCapture {
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

    [Flags]
    public enum AUDCLNT_SHAREMODE {
        SHARED = 0,
        EXCLUSIVE = 1
    }

    [Flags]
    public enum AUDCLNT_STREAMFLAGS {
        NONE = 0,
        LOOPBACK = 0x2000,
        EVENTCALLBACK = 0x40000,
        NOPERSIST = 0x80000
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct REFERENCE_TIME {
        public long Value;
    }

    [ComImport]
    [Guid("F294ACFC-3146-4483-A7BF-ADDCA7C260E2")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IAudioRenderClient {
        void GetBuffer(ref uint NumFramesRequested, out IntPtr ppData);
        void ReleaseBuffer(uint NumFramesWritten, uint dwFlags);
    }

    [ComImport]
    [Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IAudioCaptureClient {
        void GetBuffer(out IntPtr ppData, out uint pNumFramesToRead, out uint pdwFlags, out long pu64DevicePosition, out long pu64QPCPosition);
        void ReleaseBuffer(uint NumFramesRead);
        void GetNextPacketSize(out uint pNumFramesInNextPacket);
    }

    [ComImport]
    [Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IAudioClient {
        void Initialize(AUDCLNT_SHAREMODE ShareMode, AUDCLNT_STREAMFLAGS StreamFlags, REFERENCE_TIME hnsBufferDuration, REFERENCE_TIME hnsPeriodicity, ref WAVEFORMATEX pFormat, Guid AudioSessionGuid);
        void GetBufferSize(out uint pNumBufferFrames);
        void GetStreamLatency(out REFERENCE_TIME phnsLatency);
        void GetCurrentPadding(out uint pNumPaddingFrames);
        void IsFormatSupported(AUDCLNT_SHAREMODE ShareMode, ref WAVEFORMATEX pFormat, out IntPtr ppClosestMatch);
        void GetMixFormat(out IntPtr ppDeviceFormat);
        void GetDevicePeriod(out REFERENCE_TIME phnsDefaultDevicePeriod, out REFERENCE_TIME phnsMinimumDevicePeriod);
        void Start();
        void Stop();
        void Reset();
        void SetEventHandle(IntPtr eventHandle);
        void GetService(Guid riid, out IntPtr ppv);
    }

    [ComImport]
    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDevice {
        void Activate(Guid iid, uint dwClsCtx, IntPtr pActivationParams, out IntPtr ppInterface);
        void OpenPropertyStore(uint stgmAccess, out IntPtr ppProperties);
        void GetId(out IntPtr ppstrId);
        void GetState(out uint pdwState);
    }

    [ComImport]
    [Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDeviceCollection {
        void GetCount(out uint pcDevices);
        void Item(uint nDevice, out IMMDevice ppDevice);
    }

    [ComImport]
    [Guid("7991EEC9-7E89-4D85-8390-6C703CEC60C0")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    public interface IMMDeviceEnumerator {
        void EnumAudioEndpoints(uint dataFlow, uint dwStateMask, out IMMDeviceCollection ppDevices);
        void GetDefaultAudioEndpoint(uint dataFlow, uint role, out IMMDevice ppDevice);
        void GetDevice(string pwstrId, out IMMDevice ppDevice);
        void RegisterEndpointNotificationCallback(IntPtr pClient);
        void UnregisterEndpointNotificationCallback(IntPtr pClient);
    }

    [DllImport("ole32.dll")]
    public static extern int CoCreateInstance(ref Guid clsid, IntPtr pUnkOuter, uint dwClsContext, ref Guid iid, out IntPtr ppv);

    public const uint CLSCTX_ALL = 23;
    public const uint DEVICE_STATE_ACTIVE = 1;
    public const uint eRender = 0;
    public const uint eCapture = 1;
    public const uint eAll = 2;

    public static Guid CLSID_MMDeviceEnumerator = new Guid("BCDE0395-E52F-467C-8E3D-C4579291692E");
    public static Guid IID_IMMDeviceEnumerator = new Guid("A95664D2-9614-4F35-A746-DE8DB63617E6");
    public static Guid IID_IAudioClient = new Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2");
    public static Guid IID_IAudioCaptureClient = new Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317");

    public static IMMDeviceEnumerator CreateDeviceEnumerator() {
        IntPtr pEnumerator = IntPtr.Zero;
        Guid clsid = CLSID_MMDeviceEnumerator;
        Guid iid = IID_IMMDeviceEnumerator;

        int hr = CoCreateInstance(ref clsid, IntPtr.Zero, CLSCTX_ALL, ref iid, out pEnumerator);
        if (hr != 0) throw new Exception("Failed to create device enumerator");

        return (IMMDeviceEnumerator)Marshal.GetObjectForIUnknown(pEnumerator);
    }
}
"@

try {
    # Initialize COM
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject([System.Runtime.InteropServices.Marshal]::GetActiveObject("MMDeviceEnumerator"))
} catch {
    # COM not initialized, continue
}

# Create device enumerator
$enumerator = [WasapiLoopbackCapture]::CreateDeviceEnumerator()

# Get default render device (speakers)
$device = $null
if ($DeviceId) {
    $enumerator.GetDevice($DeviceId, [ref]$device)
} else {
    $enumerator.GetDefaultAudioEndpoint([WasapiLoopbackCapture]::eRender, 1, [ref]$device) # eMultimedia
}

if (-not $device) {
    Write-Error "Failed to get audio device"
    exit 1
}

# Activate audio client for loopback capture
$audioClient = $null
$device.Activate([WasapiLoopbackCapture]::IID_IAudioClient, [WasapiLoopbackCapture]::CLSCTX_ALL, [IntPtr]::Zero, [ref]$audioClient)

# Get mix format
$mixFormatPtr = [IntPtr]::Zero
$audioClient.GetMixFormat([ref]$mixFormatPtr)
$mixFormat = [System.Runtime.InteropServices.Marshal]::PtrToStructure($mixFormatPtr, [type][WasapiLoopbackCapture+WAVEFORMATEX])

# Initialize audio client for loopback
$bufferDuration = [WasapiLoopbackCapture+REFERENCE_TIME]::new()
$bufferDuration.Value = 10000000L # 1 second in 100-nanosecond units

$audioClient.Initialize(
    [WasapiLoopbackCapture+AUDCLNT_SHAREMODE]::SHARED,
    [WasapiLoopbackCapture+AUDCLNT_STREAMFLAGS]::LOOPBACK,
    $bufferDuration,
    $bufferDuration,
    [ref]$mixFormat,
    [Guid]::Empty
)

# Get capture client
$captureClient = $null
$audioClient.GetService([WasapiLoopbackCapture]::IID_IAudioCaptureClient, [ref]$captureClient)

# Get buffer size
$bufferFrameCount = 0
$audioClient.GetBufferSize([ref]$bufferFrameCount)

# Start capture
$audioClient.Start()

# Main capture loop
$running = $true
$buffer = New-Object byte[] ($bufferFrameCount * $mixFormat.nBlockAlign)

while ($running) {
    try {
        $packetLength = 0
        $captureClient.GetNextPacketSize([ref]$packetLength)

        if ($packetLength -gt 0) {
            $dataPtr = [IntPtr]::Zero
            $framesRead = 0
            $flags = 0
            $devicePosition = 0L
            $qpcPosition = 0L

            $captureClient.GetBuffer([ref]$dataPtr, [ref]$framesRead, [ref]$flags, [ref]$devicePosition, [ref]$qpcPosition)

            if ($framesRead -gt 0 -and $dataPtr -ne [IntPtr]::Zero) {
                # Copy audio data to buffer
                [System.Runtime.InteropServices.Marshal]::Copy($dataPtr, $buffer, 0, $framesRead * $mixFormat.nBlockAlign)

                # Output raw PCM data to stdout
                [Console]::OpenStandardOutput().Write($buffer, 0, $framesRead * $mixFormat.nBlockAlign)
            }

            $captureClient.ReleaseBuffer($framesRead)
        }

        # Small delay to prevent busy waiting
        Start-Sleep -Milliseconds 10

    } catch {
        Write-Error "Capture error: $_"
        $running = $false
    }
}

# Cleanup
$audioClient.Stop()
[void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($captureClient)
[void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($audioClient)
[void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($device)
[void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($enumerator)