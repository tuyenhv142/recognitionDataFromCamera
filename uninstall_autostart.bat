@echo off
chcp 65001 > nul
title Uninstall 24/7 Windows Autostart
powershell -Command "Remove-Item -Force ([Environment]::GetFolderPath('Startup') + '\CameraOCR_24h.lnk') -ErrorAction SilentlyContinue"
echo [*] Successfully removed Windows Startup entry.
pause
