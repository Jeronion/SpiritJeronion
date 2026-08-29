@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Stop-SpiritJeronion.ps1"
if errorlevel 1 pause
