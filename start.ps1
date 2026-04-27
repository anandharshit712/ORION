# ============================================================
#  ORION - AREP Dev Server (PowerShell)
#  Starts FastAPI backend + Vite frontend in separate windows.
#  Usage:
#    .\start.ps1              # with --reload
#    .\start.ps1 -NoReload    # without --reload
#
#  If you get an execution-policy error, run once per machine:
#    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#  Or bypass for a single invocation:
#    powershell -ExecutionPolicy Bypass -File .\start.ps1
# ============================================================

[CmdletBinding()]
param(
    [switch]$NoReload
)

$ErrorActionPreference = 'Stop'

$Root        = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir  = Join-Path $Root 'arep_implementation'
$FrontendDir = Join-Path $Root 'orion-frontend'

$UvicornArgs = 'arep.api.app:app --host 0.0.0.0 --port 8000'
if (-not $NoReload) { $UvicornArgs += ' --reload' }

Write-Host ''
Write-Host '  +=======================================+' -ForegroundColor Cyan
Write-Host '  |     ORION  -  AREP  Dev Server        |' -ForegroundColor Cyan
Write-Host '  +=======================================+' -ForegroundColor Cyan
Write-Host ''

# --- dependency checks ---------------------------------------------------
function Test-PythonUvicorn {
    try {
        $null = & python -m uvicorn --version 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

if (-not (Test-PythonUvicorn)) {
    Write-Host '[ERROR] uvicorn not found in the active Python environment.' -ForegroundColor Red
    Write-Host '        Run:  cd arep_implementation; pip install -e ".[api]"' -ForegroundColor Red
    exit 1
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host '[ERROR] npm not found. Install Node.js from https://nodejs.org' -ForegroundColor Red
    exit 1
}

# --- launch backend in its own PowerShell window -------------------------
Write-Host '[ORION] Starting backend  ->  http://localhost:8000  (docs: /docs)' -ForegroundColor Green
$backendCmd = "Set-Location -LiteralPath '$BackendDir'; python -m uvicorn $UvicornArgs"
Start-Process -FilePath 'powershell.exe' `
    -ArgumentList '-NoExit', '-NoProfile', '-Command', $backendCmd `
    -WorkingDirectory $BackendDir | Out-Null

# give uvicorn a moment to bind the port before Vite opens the browser
Start-Sleep -Seconds 2

# --- launch frontend in its own PowerShell window ------------------------
Write-Host '[ORION] Starting frontend ->  http://localhost:5173' -ForegroundColor Cyan
$frontendCmd = "Set-Location -LiteralPath '$FrontendDir'; npm run dev"
Start-Process -FilePath 'powershell.exe' `
    -ArgumentList '-NoExit', '-NoProfile', '-Command', $frontendCmd `
    -WorkingDirectory $FrontendDir | Out-Null

Write-Host ''
Write-Host '  Both services are running in separate windows.' -ForegroundColor Green
Write-Host '  Backend   ->  http://localhost:8000  (API docs: /docs)'
Write-Host '  Frontend  ->  http://localhost:5173'
Write-Host ''
Write-Host '  Close the backend / frontend windows individually to stop each service.'
Write-Host ''
