# Removes an install made by install.ps1 or install-exe.ps1: the app folder,
# the Start Menu group, any Desktop shortcut, and the Apps & features entry.
# A copy of this script (plus uninstall.cmd) is installed into the app folder
# so it can be run without the original download.
#
# Note: FrameworkGUI-Setup.exe installs are removed by *their* own
# uninstaller (Start Menu > Framework System GUI > Uninstall), not this one.

param([switch]$Relaunched)

$ErrorActionPreference = "SilentlyContinue"

$AppDir = Join-Path $env:LOCALAPPDATA "FrameworkGUI"
$Programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$GroupDir = Join-Path $Programs "Framework System GUI"
$LegacyLnk = Join-Path $Programs "Framework System GUI.lnk"
$DesktopLnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Framework System GUI.lnk"
$RegKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\FrameworkGUI"

$Here = $PSScriptRoot
if (-not $Here) { $Here = Split-Path -Parent $MyInvocation.MyCommand.Path }

# The installed copy lives inside the directory it is about to delete, and
# Windows will not remove a directory a running script is being read from.
# Re-run from a temp copy in that case.
if (-not $Relaunched -and $Here -and
    ($Here.TrimEnd('\') -ieq $AppDir.TrimEnd('\'))) {
    $tmp = Join-Path $env:TEMP "FrameworkGUI-uninstall.ps1"
    Copy-Item -LiteralPath $MyInvocation.MyCommand.Path -Destination $tmp -Force
    Start-Process powershell -WorkingDirectory $env:TEMP -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$tmp`"", "-Relaunched")
    return
}

Remove-Item -Recurse -Force $AppDir
Remove-Item -Recurse -Force $GroupDir
Remove-Item -Force $LegacyLnk
Remove-Item -Force $DesktopLnk
Remove-Item -Recurse -Force $RegKey

if (Test-Path $AppDir) {
    Write-Host "Some files could not be removed from $AppDir - close the app and re-run."
} else {
    Write-Host "Uninstalled Framework System GUI."
}
Read-Host "Press Enter to close" | Out-Null
