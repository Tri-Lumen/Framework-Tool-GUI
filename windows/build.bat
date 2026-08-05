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
REM Every module framework_gui.py imports has to come along. Miss one and
REM PyInstaller happily builds an exe that dies with ModuleNotFoundError on
REM launch - invisible from a source checkout, where the import works.
REM tests/test_packaging.py fails if this list falls behind the repo.
for %%M in (framework_gui.py app_icon.py appstate.py backdrop.py deps.py device_images.py drivers.py module_icons.py navigation.py parsers.py power.py theme.py widgets.py) do (
    copy /y "%SRC%..\%%M" "%WORK%\" >nul || (
        echo Could not copy %%M - check the share is reachable.
        goto :fail
    )
)

REM The device photographs the Overview shows. --add-data below is what
REM carries them into the exe; device_images.py finds them again through
REM sys._MEIPASS.
xcopy /e /i /y "%SRC%..\assets" "%WORK%\assets" >nul || (
    echo Could not copy the assets directory - check the share is reachable.
    goto :fail
)

pushd "%WORK%" || goto :fail
REM PySide6-Essentials rather than the full PySide6: the app uses
REM QtWidgets, QtGui, QtCore and QtSvg, and the extras (WebEngine, 3D,
REM Charts) would add hundreds of megabytes to the exe for nothing.
%PY% -m pip install --upgrade pyinstaller "PySide6-Essentials>=6.6" || (popd & goto :fail)
REM --icon is what puts the Framework mark on the exe itself (Explorer,
REM the taskbar, Alt-Tab). The same .ico is bundled via --add-data so the
REM running app can load it for its window icon through sys._MEIPASS.
%PY% -m PyInstaller --onefile --noconsole --uac-admin --name FrameworkGUI ^
    --icon "assets\icons\FrameworkGUI.ico" ^
    --add-data "assets;assets" framework_gui.py || (popd & goto :fail)
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
