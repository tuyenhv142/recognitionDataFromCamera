@echo off
chcp 65001 > nul
title Camera OCR Logger - 24/7 RUNNER (AUTO-RECOVERY)
echo =============================================================
echo     LIVE CAMERA OCR DATA LOGGER - 24/7 CONTINUOUS RUNNER
echo =============================================================
echo [*] Automatic LAN camera reconnection enabled.
echo [*] Daily CSV rotation enabled (readings_YYYY-MM-DD.csv).
echo [*] Automatic process restart enabled if crashed or closed.
echo [*] Opening dashboard at http://localhost:5055 ...
echo.

start "" timeout /t 2 >nul & start http://localhost:5055

:loop
echo [%date% %time%] [*] Running Camera OCR system...
python app.py
echo.
echo [!] [%date% %time%] Warning: Application exited or crashed!
echo [*] Automatically restarting in 3 seconds...
timeout /t 3 > nul
goto loop
