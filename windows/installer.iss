; Inno Setup script - produces FrameworkGUI-Setup.exe
; Prereq: run build.bat first so dist\FrameworkGUI.exe exists.
; Compile with Inno Setup 6 (https://jrsoftware.org/isinfo.php).

[Setup]
AppName=Framework System GUI
AppVersion=1.0
AppPublisher=Unofficial
DefaultDirName={autopf}\Framework System GUI
DefaultGroupName=Framework System GUI
OutputBaseFilename=FrameworkGUI-Setup
OutputDir=dist
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
UninstallDisplayName=Framework System GUI

[Files]
Source: "dist\FrameworkGUI.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Framework System GUI"; Filename: "{app}\FrameworkGUI.exe"
Name: "{autodesktop}\Framework System GUI"; Filename: "{app}\FrameworkGUI.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\FrameworkGUI.exe"; Description: "Launch Framework System GUI"; Flags: postinstall nowait skipifsilent shellexec
