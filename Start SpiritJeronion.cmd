@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\Start-SpiritJeronion.ps1"
if errorlevel 1 pause

