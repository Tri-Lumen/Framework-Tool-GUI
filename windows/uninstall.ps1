$ErrorActionPreference = "SilentlyContinue"
Remove-Item -Recurse -Force (Join-Path $env:LOCALAPPDATA "FrameworkGUI")
Remove-Item -Force (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Framework System GUI.lnk")
Remove-Item -Force (Join-Path ([Environment]::GetFolderPath("Desktop")) "Framework System GUI.lnk")
Write-Host "Uninstalled."
Read-Host "Press Enter to close" | Out-Null
