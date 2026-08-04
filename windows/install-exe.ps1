# Deploys the built FrameworkGUI.exe on this machine:
# copies dist\FrameworkGUI.exe (next to this script, e.g. on the SMB share)
# to local disk, ships an uninstaller alongside it, and creates the Start
# Menu entries.
# Prereq: someone ran build.bat once so windows\dist\FrameworkGUI.exe exists.
# Launch via install-exe.cmd (double-click) when running from a share.
#
# If you just want a normal Windows install, use FrameworkGUI-Setup.exe from
# the Releases page instead - this script is for the build-once-centrally,
# deploy-from-a-share workflow.

$ErrorActionPreference = "Stop"

function Pause-IfConsole {
    if ($Host.Name -eq "ConsoleHost") { Read-Host "`nPress Enter to close" | Out-Null }
}

try {
    $Here = $PSScriptRoot
    if (-not $Here) { $Here = Split-Path -Parent $MyInvocation.MyCommand.Path }
    $SrcExe = Join-Path $Here "dist\FrameworkGUI.exe"
    $AppDir = Join-Path $env:LOCALAPPDATA "FrameworkGUI"
    $Programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $GroupDir = Join-Path $Programs "Framework System GUI"
    $LegacyLnk = Join-Path $Programs "Framework System GUI.lnk"
    $Shortcut = Join-Path $GroupDir "Framework System GUI.lnk"
    $UninstLnk = Join-Path $GroupDir "Uninstall Framework System GUI.lnk"
    $RegKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\FrameworkGUI"

    Write-Host "== Framework System GUI exe deploy =="

    if (-not (Test-Path $SrcExe)) {
        throw "Not found: $SrcExe`nRun build.bat first (on any Windows machine with Python) so the exe exists."
    }

    # Copy exe to local disk; strip Mark-of-the-Web from the local copy
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    Copy-Item -LiteralPath $SrcExe -Destination (Join-Path $AppDir "FrameworkGUI.exe") -Force
    Unblock-File -Path (Join-Path $AppDir "FrameworkGUI.exe") -ErrorAction SilentlyContinue
    Write-Host "Copied exe to $AppDir"

    # Ship the uninstaller *with* the install, not only on the share the
    # install came from - that share may be gone when someone wants it.
    foreach ($f in @("uninstall.ps1", "uninstall.cmd")) {
        $src = Join-Path $Here $f
        if (-not (Test-Path $src)) { throw "$f is missing next to this script." }
        Copy-Item -LiteralPath $src -Destination (Join-Path $AppDir $f) -Force
        Unblock-File -Path (Join-Path $AppDir $f) -ErrorAction SilentlyContinue
    }
    $license = Join-Path $Here "..\LICENSE"
    if (Test-Path $license) { Copy-Item -LiteralPath $license -Destination $AppDir -Force }
    Write-Host "Installed uninstaller to $AppDir\uninstall.cmd"

    # framework_tool present?
    if (-not (Get-Command "framework_tool.exe" -ErrorAction SilentlyContinue)) {
        $ans = Read-Host "framework_tool not found. Install via winget now? [y/N]"
        if ($ans -match '^[Yy]') { winget install framework_tool --source winget }
        else { Write-Host "Skipping - set the binary path in the GUI top bar later." }
    }

    # Start Menu entries, in their own group so the app and its uninstaller
    # sit together. Earlier versions dropped a bare .lnk straight into
    # Programs\ - remove it so upgraders don't end up with both.
    if (Test-Path $LegacyLnk) { Remove-Item -Force $LegacyLnk }
    New-Item -ItemType Directory -Force -Path $GroupDir | Out-Null

    # No run-as-admin flag needed on the app shortcut: the exe's embedded
    # manifest (--uac-admin) makes it self-elevate.
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($Shortcut)
    $lnk.TargetPath = Join-Path $AppDir "FrameworkGUI.exe"
    $lnk.WorkingDirectory = $AppDir
    $lnk.Description = "Control Framework laptop firmware settings"
    $lnk.Save()

    $ulnk = $ws.CreateShortcut($UninstLnk)
    $ulnk.TargetPath = Join-Path $AppDir "uninstall.cmd"
    # Deliberately not $AppDir: a working directory inside the folder being
    # deleted holds it open.
    $ulnk.WorkingDirectory = $env:LOCALAPPDATA
    $ulnk.Description = "Remove Framework System GUI"
    $ulnk.Save()
    Write-Host "Created Start Menu group 'Framework System GUI' (app + uninstaller)."

    # Apps & features entry, so it also uninstalls the way users expect.
    New-Item -Path $RegKey -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name DisplayName -Value "Framework System GUI" -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name Publisher -Value "Tri-Lumen" -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name InstallLocation -Value $AppDir -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name DisplayIcon -Value (Join-Path $AppDir "FrameworkGUI.exe") -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name UninstallString `
        -Value "powershell -NoProfile -ExecutionPolicy Bypass -File `"$AppDir\uninstall.ps1`"" -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null

    $ans = Read-Host "Also create a Desktop shortcut? [y/N]"
    if ($ans -match '^[Yy]') {
        Copy-Item $Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Framework System GUI.lnk") -Force
    }

    Write-Host "`nDone. It should appear in the Start Menu immediately (search 'Framework')."
    Write-Host "To remove it later: Start Menu > Framework System GUI > Uninstall,"
    Write-Host "or Settings > Apps, or run $AppDir\uninstall.cmd."
}
catch {
    Write-Host "`nDEPLOY FAILED: $($_.Exception.Message)" -ForegroundColor Red
}
Pause-IfConsole
