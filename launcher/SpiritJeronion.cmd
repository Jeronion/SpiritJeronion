@echo off
title SpiritJeronion
echo.
echo [1] Start SpiritJeronion
echo [2] Stop SpiritJeronion
echo.
choice /c 12 /n /m "Choose 1 or 2: "
if errorlevel 2 goto stop

:start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0internal\Start-SpiritJeronion.ps1"
if errorlevel 1 pause
goto end

:stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0internal\Stop-SpiritJeronion.ps1"
if errorlevel 1 pause

:end
