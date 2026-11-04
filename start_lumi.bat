@echo off
rem LUMI launcher — web UI (localhost). CLI chahiye toh: python main.py
cd /d "%~dp0"
if not exist workspace mkdir workspace
python main.py --web
pause
