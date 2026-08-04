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
for %%M in (framework_gui.py parsers.py power.py deps.py drivers.py) do (
    copy /y "%SRC%..\%%M" "%WORK%\" >nul || (
        echo Could not copy %%M - check the share is reachable.
        goto :fail
    )
)

pushd "%WORK%" || goto :fail
%PY% -m pip install --upgrade pyinstaller || (popd & goto :fail)
%PY% -m PyInstaller --onefile --noconsole --uac-admin --name FrameworkGUI framework_gui.py || (popd & goto :fail)
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
