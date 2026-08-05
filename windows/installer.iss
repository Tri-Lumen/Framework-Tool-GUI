; Inno Setup script - produces dist\FrameworkGUI-Setup.exe
; Prereq: run build.bat first so dist\FrameworkGUI.exe exists.
; Compile with Inno Setup 6 (https://jrsoftware.org/isinfo.php):
;
;   ISCC.exe /DAppVersion=1.2.3 installer.iss
;
; CI compiles this on every push (.github/actions/build-windows) and the
; release workflow attaches the result to the GitHub Release.

; Overridable from the command line; the default is only for local runs.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Framework System GUI"
#define AppExe "FrameworkGUI.exe"
#define AppUrl "https://github.com/Tri-Lumen/Framework-Tool-GUI"

[Setup]
; Stable identity - this is what ties an upgrade (and the uninstaller entry
; in Apps & features) to a previous install. Never change it.
AppId={{8F3C1D2A-5B47-4E6A-9C1F-2D7E4B8A6C31}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Tri-Lumen
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=FrameworkGUI-Setup
OutputDir=dist
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
LicenseFile=..\LICENSE
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
; The Framework mark, on the setup wizard and on the Apps & features entry.
; The exe carries the same .ico via PyInstaller's --icon, so the Start Menu
; shortcuts below need no IconFilename of their own.
SetupIconFile=..\frameworkgui\assets\icons\FrameworkGUI.ico
WizardStyle=modern

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Setup writes its own uninstaller (unins000.exe) into {app}; these put both
; the app and that uninstaller in the Start Menu group.
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: postinstall nowait skipifsilent shellexec
