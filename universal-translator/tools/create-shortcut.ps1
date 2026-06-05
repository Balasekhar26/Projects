$root = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $root "run.exe"
$shortcut = Join-Path $env:USERPROFILE "Desktop\ULT Translator.lnk"

# Create desktop shortcut pointing to run.exe
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut($shortcut)
$lnk.TargetPath = $launcher
$lnk.Arguments = ""
$lnk.WorkingDirectory = $root
$lnk.WindowStyle = 1
$lnk.Description = "Universal Language Translator"
$lnk.Save()

if (Test-Path $shortcut) {
    Write-Host "Desktop shortcut created: $shortcut"
} else {
    Write-Host "Shortcut creation failed"
}
