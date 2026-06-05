param(
  [ValidateSet("apk", "aab")]
  [string]$Target = "apk"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$androidRoot = Join-Path $root "apps\\android"
$gradlew = Join-Path $androidRoot "gradlew.bat"
$configureAndroidEnv = Join-Path $root "tools\\configure-android-env.ps1"

if (-not (Test-Path $gradlew)) {
  throw "Android Gradle wrapper is missing at $gradlew"
}

function Get-AndroidSdkRoot {
  if ($env:ANDROID_HOME -and (Test-Path $env:ANDROID_HOME)) {
    return $env:ANDROID_HOME
  }

  $defaultSdkRoot = Join-Path $env:LOCALAPPDATA "Android\\Sdk"
  if (Test-Path $defaultSdkRoot) {
    return $defaultSdkRoot
  }

  return $null
}

function Test-ReleaseSigningConfigured {
  $keystoreProperties = Join-Path $androidRoot "keystore.properties"
  if (Test-Path $keystoreProperties) {
    return $true
  }

  return [bool](
    $env:ULT_ANDROID_KEYSTORE -and
    $env:ULT_ANDROID_KEYSTORE_PASSWORD -and
    $env:ULT_ANDROID_KEY_ALIAS -and
    $env:ULT_ANDROID_KEY_PASSWORD
  )
}

$sdkRoot = Get-AndroidSdkRoot
if (-not $sdkRoot) {
  throw "Android SDK not found. Install Android Studio, then install Platform-Tools and Command-line Tools from SDK Manager."
}

if (Test-Path $configureAndroidEnv) {
  & $configureAndroidEnv -SdkRoot $sdkRoot -Quiet | Out-Null
}

$env:ANDROID_HOME = $sdkRoot
$platformTools = Join-Path $sdkRoot "platform-tools"
$cmdlineTools = Join-Path $sdkRoot "cmdline-tools\\latest\\bin"
$env:PATH = "$platformTools;$cmdlineTools;$env:PATH"

$adbPath = Join-Path $platformTools "adb.exe"
if (-not (Test-Path $adbPath)) {
  throw "Android SDK platform-tools are missing at $platformTools. Install Platform-Tools from Android Studio SDK Manager."
}

if (-not (Test-ReleaseSigningConfigured)) {
  throw "Android release signing is not configured. Create apps\\android\\keystore.properties from apps\\android\\keystore.properties.example or set ULT_ANDROID_KEYSTORE / ULT_ANDROID_KEYSTORE_PASSWORD / ULT_ANDROID_KEY_ALIAS / ULT_ANDROID_KEY_PASSWORD."
}

Push-Location $androidRoot
try {
  if ($Target -eq "apk") {
    & $gradlew assembleRelease
  } else {
    & $gradlew bundleRelease
  }
} finally {
  Pop-Location
}
