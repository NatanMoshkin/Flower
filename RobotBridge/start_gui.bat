@echo off
REM Double-clickable wrapper — launches the Robot Bridge Monitor & Tester GUI.
setlocal
cd /d "%~dp0"
pythonw bridge_gui.py --config config.yaml
if errorlevel 1 (
  REM pythonw suppresses stderr — retry with python.exe so the user sees errors
  python bridge_gui.py --config config.yaml
  pause
)
