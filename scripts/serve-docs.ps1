# Serves the Flower repo root over HTTP and opens the docs index in your default browser.
# The viewer.html markdown renderer needs HTTP because fetch() is blocked under file://.
#
# Usage:  double-click scripts\serve-docs.bat, or from a shell:
#         powershell -ExecutionPolicy Bypass -File scripts\serve-docs.ps1
#         powershell -ExecutionPolicy Bypass -File scripts\serve-docs.ps1 -Port 8766
#
# Ctrl+C in the terminal window to stop the server.

param(
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'

# Resolve the repo root from this script's location (scripts/ is a direct child of the repo root).
$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $RepoRoot) { $RepoRoot = (Get-Location).Path }

Write-Host ""
Write-Host "  Flower  --  serve-docs" -ForegroundColor Cyan
Write-Host "  Repo root: $RepoRoot" -ForegroundColor Gray
Write-Host ""

# ---- Sanity check: are we really in the Flower repo? -----------------------
$indexHtml = Join-Path $RepoRoot 'docs\index.html'
if (-not (Test-Path $indexHtml)) {
    Write-Host "  docs\index.html not found under $RepoRoot" -ForegroundColor Red
    Write-Host "  Are you running this from the Flower repo's scripts\ folder?" -ForegroundColor Red
    exit 1
}

# ---- Locate python ---------------------------------------------------------
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $python) {
    $python = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        Write-Host "  python.exe / py.exe not found on PATH. Install Python 3.9+ or activate the project venv." -ForegroundColor Red
        exit 1
    }
}

# ---- Handle a stale server on the same port --------------------------------
# The URL http://127.0.0.1:$Port/docs/index.html is the same regardless of which
# repo the server is running from. If another repo's docs server is still bound
# on this port, silently reusing it would serve THAT repo's docs and confuse
# the user. So: kill any Python http.server on this port, refuse anything else.
$existing = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($existing) {
    $ownerPid  = $existing[0].OwningProcess
    $ownerProc = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerPid" -ErrorAction SilentlyContinue
    $isOursSh  = $ownerProc -and ($ownerProc.Name -match '^py(w?|thon(w?|3)?)\.exe$') -and ($ownerProc.CommandLine -match 'http\.server')
    if ($isOursSh) {
        Write-Host "  Port $Port already has a python http.server (PID $ownerPid). Stopping it before starting ours." -ForegroundColor Yellow
        Write-Host "    old cmdline: $($ownerProc.CommandLine)" -ForegroundColor DarkGray
        Stop-Process -Id $ownerPid -Force
        # Wait for the socket to drain
        $deadline = (Get-Date).AddSeconds(5)
        while ((Get-Date) -lt $deadline) {
            if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) { break }
            Start-Sleep -Milliseconds 150
        }
        if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
            Write-Host "  Port $Port did not free after stopping the old server. Aborting." -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "  Port $Port is in use by PID $ownerPid  ($($ownerProc.Name))." -ForegroundColor Red
        Write-Host "  It doesn't look like a docs server, so this script won't touch it." -ForegroundColor Red
        Write-Host "  Either free the port, or re-run with:  serve-docs.ps1 -Port 8766" -ForegroundColor Red
        exit 1
    }
}

# ---- Start our own server --------------------------------------------------
Write-Host "  Starting python -m http.server $Port from $RepoRoot ..." -ForegroundColor Cyan
Start-Job -Name "docs-http-server" -ScriptBlock {
    param($root, $port, $python)
    Set-Location $root
    & $python -m http.server $port --bind 127.0.0.1
} -ArgumentList $RepoRoot, $Port, $python | Out-Null

# Wait for the port to come up
$deadline = (Get-Date).AddSeconds(5)
while ((Get-Date) -lt $deadline) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { break }
    Start-Sleep -Milliseconds 100
}
if (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
    Write-Host "  Server didn't come up on port $Port within 5s." -ForegroundColor Red
    Get-Job -Name "docs-http-server" -ErrorAction SilentlyContinue | Receive-Job
    Get-Job -Name "docs-http-server" -ErrorAction SilentlyContinue | Remove-Job -Force
    exit 1
}

# ---- Verify we're actually serving Flower docs ----------------------------
# Fetches the index and looks for the expected title. Prevents surprises when
# something else is hooked into the same port or when a proxy is in the way.
$Url = "http://127.0.0.1:$Port/docs/index.html"
try {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    # Match on <title> — the em dash character between "Flower" and
    # "Documentation Index" varies by encoding, so allow any chars between.
    if ($r.Content -match '<title>\s*Flower[^<]*Documentation Index[^<]*</title>') {
        Write-Host "  Verified: Flower docs index is being served." -ForegroundColor Green
    } else {
        Write-Host "  WARNING: $Url did not return a page whose title looks like Flower's docs index." -ForegroundColor Yellow
        Write-Host "  Something else may be responding on port $Port. Consider -Port 8766." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Could not fetch $Url  ($_)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Opening $Url" -ForegroundColor Cyan
Start-Process $Url

Write-Host ""
Write-Host "  Docs are being served. Ctrl+C in this window to stop." -ForegroundColor Green
Write-Host "  Server root: $RepoRoot"
Write-Host "  Index URL:   $Url"
Write-Host ""

# Keep the parent shell alive so Ctrl+C stops the job (jobs die with the shell).
try {
    Wait-Job -Name "docs-http-server" | Out-Null
} finally {
    Get-Job -Name "docs-http-server" -ErrorAction SilentlyContinue | Stop-Job
    Get-Job -Name "docs-http-server" -ErrorAction SilentlyContinue | Remove-Job -Force
}
