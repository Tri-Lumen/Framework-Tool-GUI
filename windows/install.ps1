# Framework System GUI - Windows installer (SMB-safe)
# Installs the Python script version - needs Python on this machine. For a
# no-Python install use FrameworkGUI-Setup.exe from the Releases page.
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
    $Programs = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $GroupDir = Join-Path $Programs "Framework System GUI"
    $LegacyLnk = Join-Path $Programs "Framework System GUI.lnk"
    $Shortcut = Join-Path $GroupDir "Framework System GUI.lnk"
    $UninstLnk = Join-Path $GroupDir "Uninstall Framework System GUI.lnk"
    $RegKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\FrameworkGUI"
    # All of these are required: framework_gui.py imports the rest, and a
    # missing one only shows up as ModuleNotFoundError at launch.
    $SrcFiles = @("framework_gui.py", "appstate.py", "backdrop.py",
                  "deps.py", "device_images.py", "drivers.py",
                  "module_icons.py", "navigation.py", "parsers.py",
                  "power.py", "theme.py",
                  "widgets.py") | ForEach-Object { Join-Path $Here "..\$_" }
    $SrcAssets = Join-Path $Here "..\assets"

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

    # 1b) PySide6, which the UI is built on. The script install runs from a
    # system Python, so this is the one dependency it cannot assume; the
    # packaged exe has it built in and needs none of this.
    $python = Join-Path (Split-Path -Parent $pythonw) "python.exe"
    & $python -c "import PySide6" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing PySide6 (the GUI toolkit) for this Python..."
        & $python -m pip install --upgrade "PySide6-Essentials>=6.6"
        if ($LASTEXITCODE -ne 0) {
            throw "Could not install PySide6. Install it by hand and re-run: python -m pip install PySide6-Essentials"
        }
    }

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
    if (-not (Test-Path $SrcAssets)) {
        throw "assets\ not found - keep the folder structure from the repo intact."
    }
    Copy-Item -LiteralPath $SrcAssets -Destination $AppDir -Recurse -Force
    Write-Host "Installed app to $AppDir"

    # 4) Ship the uninstaller with the install, not only on the share the
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

    # 5) Start Menu entries, in their own group so the app and its
    # uninstaller sit together. Earlier versions dropped a bare .lnk straight
    # into Programs\ - remove it so upgraders don't end up with both.
    if (Test-Path $LegacyLnk) { Remove-Item -Force $LegacyLnk }
    New-Item -ItemType Directory -Force -Path $GroupDir | Out-Null

    # App shortcut targets the LOCAL copy and is marked run-as-administrator
    # (the script version has no embedded manifest to self-elevate with).
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

    $ulnk = $ws.CreateShortcut($UninstLnk)
    $ulnk.TargetPath = Join-Path $AppDir "uninstall.cmd"
    # Deliberately not $AppDir: a working directory inside the folder being
    # deleted holds it open.
    $ulnk.WorkingDirectory = $env:LOCALAPPDATA
    $ulnk.Description = "Remove Framework System GUI"
    $ulnk.Save()
    Write-Host "Created Start Menu uninstall entry."

    # 6) Apps & features entry, so it also uninstalls the way users expect.
    New-Item -Path $RegKey -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name DisplayName -Value "Framework System GUI" -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name Publisher -Value "Tri-Lumen" -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name InstallLocation -Value $AppDir -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name UninstallString `
        -Value "powershell -NoProfile -ExecutionPolicy Bypass -File `"$AppDir\uninstall.ps1`"" -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $RegKey -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null

    $ans = Read-Host "Also create a Desktop shortcut? [y/N]"
    if ($ans -match '^[Yy]') {
        Copy-Item $Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "Framework System GUI.lnk") -Force
    }

    Write-Host "`nDone. Launch 'Framework System GUI' from the Start Menu."
    Write-Host "To remove it later: Start Menu > Framework System GUI > Uninstall,"
    Write-Host "or Settings > Apps, or run $AppDir\uninstall.cmd."
}
catch {
    Write-Host "`nINSTALL FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "If PowerShell refused to run this script from the network share,"
    Write-Host "use install.cmd instead, or copy the folder locally first."
}
Pause-IfConsole
