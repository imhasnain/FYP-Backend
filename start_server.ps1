# ============================================================
# start_server.ps1 — One-click backend launcher
# Usage: Right-click → "Run with PowerShell"
#        OR from terminal: .\start_server.ps1
# ============================================================

Write-Host "=== Virtual Clinic Backend Launcher ===" -ForegroundColor Cyan

# Activate venv
$venvPath = "$PSScriptRoot\venv\Scripts\Activate.ps1"
if (Test-Path $venvPath) {
    Write-Host "Activating virtual environment..." -ForegroundColor Yellow
    & $venvPath
    Write-Host "Venv active." -ForegroundColor Green
} else {
    Write-Host "ERROR: venv not found at $venvPath" -ForegroundColor Red
    Write-Host "Run: python -m venv venv && .\venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# Show local IP for Flutter config
Write-Host ""
Write-Host "Your PC's LAN IP (for Flutter api_constants.dart):" -ForegroundColor Cyan
(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch "^127\." -and $_.IPAddress -notmatch "^169\." }) | ForEach-Object {
    Write-Host "  http://$($_.IPAddress):8000" -ForegroundColor Green
}
Write-Host ""

# Start uvicorn
Write-Host "Starting FastAPI backend on 0.0.0.0:8000..." -ForegroundColor Yellow
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
