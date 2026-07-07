@echo off
setlocal
cd /d "%~dp0"
python robot_bridge.py --config config.yaml
