# AutomatePinterest Background CDP Engine Watchdog
# Ensures the local Playwright/Edge CDP engine stays active on port 3001
# so https://automate-pinterest-eight.vercel.app/ can drive browser automation seamlessly.

$ErrorActionPreference = "SilentlyContinue"
$ProjectRoot = "c:\AutomatePinterest"
$UvicornExe = Join-Path $ProjectRoot "venv\Scripts\uvicorn.exe"
$Port = 3001

Set-Location $ProjectRoot

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $existing) {
    Start-Process -FilePath $UvicornExe `
        -ArgumentList "backend.main:app --port $Port --host 0.0.0.0" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden
}
