@echo off
REM Double-click entry point. Runs the installer with execution policy
REM bypassed - required when launching from an SMB share, where the default
REM policy treats the script as untrusted remote content and blocks it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
