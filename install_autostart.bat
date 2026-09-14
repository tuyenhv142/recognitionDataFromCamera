@echo off
chcp 65001 > nul
title Install 24/7 Windows Autostart
echo ==============================================================
echo    INSTALL 24/7 CAMERA OCR AUTOSTART WITH WINDOWS BOOT
echo ==============================================================
echo.
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([Environment]::GetFolderPath('Startup') + '\CameraOCR_24h.lnk'); $s.TargetPath = '%~dp0run_24h.bat'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 1; $s.Save()"
echo [*] Successfully created shortcut in Windows Startup folder!
echo [*] From now on, if the PC reboots or loses power, the system will AUTO-START automatically.
echo.
pause
