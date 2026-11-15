@echo off
title LUMI-OS :: Sovereign Local-First AI Software Engineer
cd /d "%~dp0"

echo.
echo  ====================================================================
echo   LUMI-OS :: ONE-CLICK BOOTSTRAPPER ^& OMNI-COCKPIT LAUNCHER
echo  ====================================================================
echo.

if not exist workspace mkdir workspace
if not exist data mkdir data

python scripts\quickstart_doctor.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [*] Installing missing Python dependencies from requirements.txt...
    pip install -r requirements.txt
)

echo.
echo  [*] Launching LUMI-OS Web Cockpit on http://127.0.0.1:8765 ...
echo  [*] Tip: Run "python scripts\run_60s_showcase.py" anytime for the 60s viral demo!
echo.
python -u main.py --web
pause
