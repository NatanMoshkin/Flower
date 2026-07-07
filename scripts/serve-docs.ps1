# Serves the repo root over HTTP and opens the docs index in your default browser.
# The viewer.html markdown renderer needs HTTP because fetch() is blocked under file://.
#
# Usage:  double-click scripts\serve-docs.bat, or from a shell:
#         powershell -ExecutionPolicy Bypass -File scripts\serve-docs.ps1
#
# Ctrl+C in the terminal window to stop the server (only when THIS script started it).

param(
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'

# Resolve the repo root from this script's location.
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }

# Prefer python.exe on PATH; fall back to `py` launcher.
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        Write-Host "python.exe / py.exe not found on PATH. Install Python 3.9+ or activate the project venv." -ForegroundColor Red
        exit 1
    }
}

# If the port is already in use, reuse it (don't spawn a second server).
$startedJob = $false
$existing = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Port $Port is already in use (PID $($existing[0].OwningProcess)). Reusing it." -ForegroundColor Yellow
} else {
    Write-Host "Serving $RepoRoot on http://127.0.0.1:$Port ..." -ForegroundColor Cyan
    # http.server as a background job so we can open the browser then hand control back.
    Start-Job -Name "docs-http-server" -ScriptBlock {
        param($root, $port, $python)
        Set-Location $root
        & $python -m http.server $port
    } -ArgumentList $RepoRoot, $Port, $python | Out-Null
    $startedJob = $true

    # Wait briefly for the port to come up (server startup is ~200 ms).
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline) {
        if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { break }
        Start-Sleep -Milliseconds 100
    }
}

$Url = "http://127.0.0.1:$Port/docs/index.html"
Write-Host "Opening $Url ..." -ForegroundColor Cyan
Start-Process $Url

Write-Host ""
if ($startedJob) {
    Write-Host "Docs are being served. Ctrl+C in this window to stop." -ForegroundColor Green
    Write-Host "  Server root: $RepoRoot"
    Write-Host "  Index URL:   $Url"
    Write-Host ""

    # Keep the parent shell alive so Ctrl+C stops the job (jobs die with the shell).
    try {
        Wait-Job -Name "docs-http-server" | Out-Null
    } finally {
        Get-Job -Name "docs-http-server" -ErrorAction SilentlyContinue | Stop-Job
        Get-Job -Name "docs-http-server" -ErrorAction SilentlyContinue | Remove-Job
    }
} else {
    Write-Host "Existing server (PID $($existing[0].OwningProcess)) is still running - leaving it as-is." -ForegroundColor Green
    Write-Host "  Server root: $RepoRoot"
    Write-Host "  Index URL:   $Url"
    Write-Host ""
    Write-Host "This window did NOT start the server, so nothing to Ctrl+C here." -ForegroundColor DarkGray
    Write-Host "To stop the running server: close its original console window, or run:" -ForegroundColor DarkGray
    Write-Host "  Stop-Process -Id $($existing[0].OwningProcess) -Force" -ForegroundColor DarkGray
}
