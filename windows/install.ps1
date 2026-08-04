# Framework System GUI - Windows installer (SMB-safe)
# Preferred launch: double-click install.cmd (bypasses execution policy).
# Direct:  powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1

$ErrorActionPreference = "Stop"

function Pause-IfConsole {
    if ($Host.Name -eq "ConsoleHost") { Read-Host "`nPress Enter to close" | Out-Null }
}

try {
    $Here = $PSScriptRoot
    if (-not $Here) { $Here = Split-Path -Parent $MyInvocation.MyCommand.Path }
    $AppDir = Join-Path $env:LOCALAPPDATA "FrameworkGUI"
    $StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $Shortcut = Join-Path $StartMenu "Framework System GUI.lnk"
    # Both files are required: framework_gui.py imports parsers.py.
    $SrcFiles = @("framework_gui.py", "parsers.py") | ForEach-Object { Join-Path $Here "..\$_" }

    Write-Host "== Framework System GUI installer =="
    Write-Host "Source: $Here"

    foreach ($f in $SrcFiles) {
        if (-not (Test-Path $f)) {
            throw "$f not found - keep the folder structure from the repo intact."
        }
    }

    # 1) Find pythonw.exe
    $pythonw = $null
    $cmd = Get-Command "pythonw.exe" -ErrorAction SilentlyContinue
    if ($cmd) { $pythonw = $cmd.Source }
    if (-not $pythonw) {
        $py = Get-Command "py.exe" -ErrorAction SilentlyContinue
        if ($py) {
            $pythonw = (& $py.Source -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))").Trim()
        }
    }
    if (-not $pythonw -or -not (Test-Path $pythonw)) {
        throw "Python not found. Install it first: winget install Python.Python.3.12 - then re-run."
    }
    Write-Host "Using Python: $pythonw"

    # 2) framework_tool present?
    if (-not (Get-Command "framework_tool.exe" -ErrorAction SilentlyContinue)) {
        $ans = Read-Host "framework_tool not found. Install via winget now? [y/N]"
        if ($ans -match '^[Yy]') { winget install framework_tool --source winget }
        else { Write-Host "Skipping - set the binary path in the GUI top bar later." }
    }

    # 3) Copy app to LOCAL disk and strip Mark-of-the-Web from the copy
    New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
    foreach ($f in $SrcFiles) {
        $leaf = Split-Path -Leaf $f
        Copy-Item -LiteralPath (Resolve-Path $f) -Destination (Join-Path $AppDir $leaf) -Force
        Unblock-File -Path (Join-Path $AppDir $leaf) -ErrorAction SilentlyContinue
    }
    Write-Host "Installed app to $AppDir"

    # 4) Start Menu shortcut (targets LOCAL copy, marked run-as-administrator)
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut($Shortcut)
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = "`"$AppDir\framework_gui.py`""
    $lnk.WorkingDirectory = $AppDir
    $lnk.Description = "Control Framework laptop firmware settings"
    $lnk.Save()
    $bytes = [IO.File]::ReadAllBytes($Shortcut)
    $bytes[0x15] = $bytes[0x15] -bor 0x20   # RunAsAdministrator flag
    [IO.File]::WriteAllBytes($Shortcut, $bytes)
    Write-Host "Created Start Menu shortcut (elevated - one UAC prompt per launch)."

    $ans = Read-Host "Also create a Desktop shortcut? [y/N]"
    if ($ans -match '^[Yy]') {
        Copy-Item $Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Framework System GUI.lnk") -Force
    }

    Write-Host "`nDone. Launch 'Framework System GUI' from the Start Menu."
}
catch {
    Write-Host "`nINSTALL FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "If PowerShell refused to run this script from the network share,"
    Write-Host "use install.cmd instead, or copy the folder locally first."
}
Pause-IfConsole
