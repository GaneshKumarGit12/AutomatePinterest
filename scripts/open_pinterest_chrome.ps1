$profileDir = Join-Path $PSScriptRoot "..\user_data\pinterest_profile"
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"

if (Test-Path $chromePath) {
    Start-Process -FilePath $chromePath -ArgumentList "--user-data-dir=`"$profileDir`"", "https://www.pinterest.com/login"
    Write-Host "Google Chrome opened with AutomatePinterest profile." -ForegroundColor Green
} else {
    Start-Process "https://www.pinterest.com/login"
}
