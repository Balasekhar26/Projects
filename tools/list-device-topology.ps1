Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class WaveDevices {
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

  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct WAVEINCAPS {
    public ushort wMid;
    public ushort wPid;
    public uint vDriverVersion;

    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
    public string szPname;

    public uint dwFormats;
    public ushort wChannels;
    public ushort wReserved1;
  }

  [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
  public static extern uint waveOutGetNumDevs();

  [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
  public static extern uint waveOutGetDevCaps(
    int uDeviceID,
    out WAVEOUTCAPS caps,
    uint cbwoc
  );

  [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
  public static extern uint waveInGetNumDevs();

  [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
  public static extern uint waveInGetDevCaps(
    int uDeviceID,
    out WAVEINCAPS caps,
    uint cbwic
  );
}
"@

$systemVoice = New-Object -ComObject SAPI.SpVoice
$voiceTokens = $systemVoice.GetVoices()
$systemVoices = for ($index = 0; $index -lt $voiceTokens.Count; $index++) {
  $token = $voiceTokens.Item($index)
  [pscustomobject]@{
    id = "sapi:$($token.Id)"
    name = $token.GetDescription()
  }
}

$outputCount = [WaveDevices]::waveOutGetNumDevs()
$outputDevices = for ($index = 0; $index -lt $outputCount; $index++) {
  $caps = New-Object WaveDevices+WAVEOUTCAPS
  [void][WaveDevices]::waveOutGetDevCaps(
    $index,
    [ref]$caps,
    [uint32][Runtime.InteropServices.Marshal]::SizeOf([type]'WaveDevices+WAVEOUTCAPS')
  )

  [pscustomobject]@{
    id = "waveout:$index"
    name = $caps.szPname.Trim()
  }
}

$inputCount = [WaveDevices]::waveInGetNumDevs()
$inputDevices = for ($index = 0; $index -lt $inputCount; $index++) {
  $caps = New-Object WaveDevices+WAVEINCAPS
  [void][WaveDevices]::waveInGetDevCaps(
    $index,
    [ref]$caps,
    [uint32][Runtime.InteropServices.Marshal]::SizeOf([type]'WaveDevices+WAVEINCAPS')
  )

  [pscustomobject]@{
    id = "wavein:$index"
    name = $caps.szPname.Trim()
  }
}

[pscustomobject]@{
  inputDevices = $inputDevices
  outputDevices = $outputDevices
  systemVoices = $systemVoices
} | ConvertTo-Json -Compress
