# Deploys the built FrameworkGUI.exe on this machine:
# copies dist\FrameworkGUI.exe (next to this script, e.g. on the SMB share)
# to local disk and creates a Start Menu shortcut.
# Prereq: someone ran build.bat once so windows\dist\FrameworkGUI.exe exists.
# Launch via install-exe.cmd (double-click) when running from a share.

$ErrorActionPreference = "Stop"

function Pause-IfConsole {
    if ($Host.Name -eq "ConsoleHost") { Read-Host "`nPress Enter to close" | Out-Null }
}

try {
    $Here = $PSScriptRoot
    if (-not $Here) { $Here = Split-Path -Parent $MyInvocation.MyCommand.Path }
    $SrcExe = Join-Path $Here "dist\FrameworkGUI.exe"
    $AppDir = Join-Path $env:LOCALAPPDATA "FrameworkGUI"
    $StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $Shortcut = Join-Path $StartMenu "Framework System GUI.lnk"

    Write-Host "== Framework System GUI exe deploy =="

    if (-not (Test-Path $SrcExe)) {
        throw "Not found: $SrcExe`nRun build.bat first (on any Windows machine with Python) so the exe exists."
    }

    # Copy exe to local disk; strip Mark-of-the-Web from the local copy
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    Copy-Item -LiteralPath $SrcExe -Destination (Join-Path $AppDir "FrameworkGUI.exe") -Force
    Unblock-File -Path (Join-Path $AppDir "FrameworkGUI.exe") -ErrorAction SilentlyContinue
    Write-Host "Copied exe to $AppDir"

    # framework_tool present?
    if (-not (Get-Command "framework_tool.exe" -ErrorAction SilentlyContinue)) {
        $ans = Read-Host "framework_tool not found. Install via winget now? [y/N]"
        if ($ans -match '^[Yy]') { winget install framework_tool --source winget }
        else { Write-Host "Skipping - set the binary path in the GUI top bar later." }
    }

    # Start Menu shortcut. No run-as-admin flag needed: the exe's embedded
    # manifest (--uac-admin) makes it self-elevate.
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($Shortcut)
    $lnk.TargetPath = Join-Path $AppDir "FrameworkGUI.exe"
    $lnk.WorkingDirectory = $AppDir
    $lnk.Description = "Control Framework laptop firmware settings"
    $lnk.Save()
    Write-Host "Created Start Menu shortcut: Framework System GUI"

    $ans = Read-Host "Also create a Desktop shortcut? [y/N]"
    if ($ans -match '^[Yy]') {
        Copy-Item $Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Framework System GUI.lnk") -Force
    }

    Write-Host "`nDone. It should appear in the Start Menu immediately (search 'Framework')."
}
catch {
    Write-Host "`nDEPLOY FAILED: $($_.Exception.Message)" -ForegroundColor Red
}
Pause-IfConsole
