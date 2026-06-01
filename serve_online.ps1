# ============================================================
#  Put Jobber online (secure tunnel) so you can use it on any device.
#  Right-click -> "Run with PowerShell", or run:  .\serve_online.ps1
#  Keep this window open while you use the app. Press Ctrl+C to stop.
# ============================================================
Set-Location -Path $PSScriptRoot

# 1) Require an access password so the public link isn't open to everyone.
$pw = $null
if (Test-Path .env) {
    foreach ($line in Get-Content .env) {
        if ($line -match '^\s*JOBBER_PASSWORD\s*=\s*(\S.*?)\s*$') { $pw = $matches[1] }
    }
}
if ([string]::IsNullOrWhiteSpace($pw)) {
    Write-Host "[!] Set JOBBER_PASSWORD=something in your .env first - it protects the public link." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# 2) Locate cloudflared (bundled copy preferred, else PATH).
$cf = Join-Path $PSScriptRoot "tools\cloudflared.exe"
if (-not (Test-Path $cf)) {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { $cf = $cmd.Source }
    else {
        Write-Host "[!] cloudflared.exe not found in .\tools. Download it from:" -ForegroundColor Yellow
        Write-Host "    https://github.com/cloudflare/cloudflared/releases/latest" -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# 3) Start the app (relaxed proxy settings so it works through the tunnel).
Write-Host "Starting Jobber..." -ForegroundColor Cyan
$env:JOBBER_REQUIRE_PASSWORD = "1"   # turn the password gate ON for this online session
$st = Start-Process -FilePath "python" -PassThru -ArgumentList @(
    "-m", "streamlit", "run", "app.py",
    "--server.port", "8501", "--server.headless", "true",
    "--server.enableCORS", "false", "--server.enableXsrfProtection", "false"
)
Start-Sleep -Seconds 6

# 4) Open the secure tunnel. The public https URL prints below.
Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host " Your link will appear below - look for  https://<...>.trycloudflare.com" -ForegroundColor Green
Write-Host " Open it on any device and log in with your JOBBER_PASSWORD." -ForegroundColor Green
Write-Host " Keep this window open while using the app. Ctrl+C to stop." -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green
Write-Host ""
try {
    & $cf tunnel --url http://localhost:8501
}
finally {
    if ($st -and -not $st.HasExited) { Stop-Process -Id $st.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "Jobber stopped." -ForegroundColor Cyan
}
