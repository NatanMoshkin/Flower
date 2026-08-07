@echo off
REM ============================================================================
REM  Flower -- serve the docs so the HTML viewer works.
REM
REM  DOUBLE-CLICK THIS FILE. It serves the repo root on http://127.0.0.1:8765
REM  and opens the docs index in your browser.
REM
REM  Why a server is needed at all: docs/viewer.html renders CLAUDE.md by
REM  fetch()ing it, and Chromium and Firefox block fetch() for file:// URLs. So
REM  opening viewer.html by double-clicking it will always fail -- it has to be
REM  served over HTTP.
REM
REM  Once it is running:
REM    Docs index    http://127.0.0.1:8765/docs/index.html
REM    CLAUDE.md     http://127.0.0.1:8765/docs/viewer.html?doc=../CLAUDE.md
REM
REM  The server MUST be rooted at the repo root, not at docs/ -- the ?doc=
REM  parameter above reaches outside docs/ with .., and a docs-rooted server
REM  refuses that. This script gets it right; a manual `python -m http.server`
REM  run from the wrong directory does not.
REM
REM  Ctrl+C in this window, or just close it, to stop the server.
REM
REM  Lives in the repo ROOT deliberately, for one-click access. The PowerShell
REM  script it calls stays in scripts\ with the other tooling.
REM ============================================================================

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\serve-docs.ps1" %*
pause
