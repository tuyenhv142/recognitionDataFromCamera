@echo off
chcp 65001 > nul
title Camera OCR Data Logger
echo =======================================================
echo         LIVE CAMERA OCR DATA LOGGER SYSTEM
echo =======================================================
echo.
echo [*] Starting Web Server and connecting to Camera...
echo [*] Web browser will open automatically in a few seconds...
echo.

start "" timeout /t 2 >nul & start http://localhost:5055
python app.py

pause
