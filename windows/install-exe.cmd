@echo off
REM Double-click entry point for deploying the built exe from an SMB share.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-exe.ps1"
