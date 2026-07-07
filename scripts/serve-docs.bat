@echo off
REM Double-clickable wrapper around serve-docs.ps1.
REM Serves the repo root on http://127.0.0.1:8765 and opens the docs index.
REM Ctrl+C in this window (or close it) to stop the server.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve-docs.ps1" %*
pause
