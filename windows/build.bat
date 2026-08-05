@echo off
setlocal
REM Builds a standalone FrameworkGUI.exe.
REM SMB-safe: copies sources to a local temp dir, builds there (PyInstaller
REM and cmd do not work reliably on UNC/network paths), then copies the exe
REM back next to this script.

set "SRC=%~dp0"
set "WORK=%TEMP%\FrameworkGUI-build"

REM Prefer the py launcher; fall back to python.exe on PATH (some installs,
REM including CI images, have one but not the other).
set "PY=py"
where py >nul 2>&1
if errorlevel 1 (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python not found. Install it first:
        echo   winget install Python.Python.3.12
        goto :fail
    )
    set "PY=python"
)

if exist "%WORK%" rmdir /s /q "%WORK%"
mkdir "%WORK%" || goto :fail
REM The launcher, and the package it imports. This used to be a list of
REM module filenames that had to be edited every time a module was added -
REM and a missed one built an exe that died with ModuleNotFoundError on a
REM machine that had never seen the source. Copying the directory cannot
REM fall behind.
copy /y "%SRC%..\framework_gui.py" "%WORK%\" >nul || (
    echo Could not copy framework_gui.py - check the share is reachable.
    goto :fail
)
REM /exclude keeps __pycache__ out of the exe; the .pyc files in it are for
REM whatever Python built them, which is not necessarily this one.
xcopy /e /i /y "%SRC%..\frameworkgui" "%WORK%\frameworkgui" >nul || (
    echo Could not copy the frameworkgui package - check the share is reachable.
    goto :fail
)
if exist "%WORK%\frameworkgui\__pycache__" rmdir /s /q "%WORK%\frameworkgui\__pycache__"

pushd "%WORK%" || goto :fail
REM PySide6-Essentials rather than the full PySide6: the app uses
REM QtWidgets, QtGui and QtCore - the icons are drawn by iconpaths.py, so
REM QtSvg is not needed - and the extras (WebEngine, 3D,
REM Charts) would add hundreds of megabytes to the exe for nothing.
%PY% -m pip install --upgrade pyinstaller "PySide6-Essentials>=6.6" || (popd & goto :fail)
REM --icon is what puts the Framework mark on the exe itself (Explorer,
REM the taskbar, Alt-Tab). The same .ico is bundled via --add-data so the
REM running app can load it for its window icon through sys._MEIPASS.
REM --add-data puts the assets at the root of the unpacked tree, which is
REM where app_icon/device_images look for them via sys._MEIPASS - they live
REM inside the package in the repo, but not in the bundle.
%PY% -m PyInstaller --onefile --noconsole --uac-admin --name FrameworkGUI ^
    --icon "frameworkgui\assets\icons\FrameworkGUI.ico" ^
    --add-data "frameworkgui\assets;assets" framework_gui.py || (popd & goto :fail)
popd

if not exist "%SRC%dist" mkdir "%SRC%dist"
copy /y "%WORK%\dist\FrameworkGUI.exe" "%SRC%dist\FrameworkGUI.exe" >nul || (
    echo Build succeeded but copying the exe back to the share failed.
    echo The exe is at: %WORK%\dist\FrameworkGUI.exe
    goto :fail
)

echo.
echo Success: %SRC%dist\FrameworkGUI.exe
echo Distribute that single file, or compile installer.iss with Inno Setup
echo for a setup.exe with Start Menu entry and uninstaller.
echo.
REM Set FWGUI_NO_PAUSE=1 for unattended runs (CI).
if not defined FWGUI_NO_PAUSE pause
exit /b 0

:fail
echo.
echo BUILD FAILED - read the messages above.
echo If Windows blocked the script (downloaded/network file): right-click
echo build.bat - Properties - check "Unblock", or copy the folder locally.
echo.
if not defined FWGUI_NO_PAUSE pause
exit /b 1
