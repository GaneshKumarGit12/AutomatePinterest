$src = Join-Path $env:LOCALAPPDATA "Microsoft\Edge\User Data"
$dst = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\user_data\automation_session"))

# Copy Local State
if (Test-Path "$src\Local State") {
    New-Item -ItemType Directory -Path $dst -Force | Out-Null
    Copy-Item -Path "$src\Local State" -Destination "$dst\Local State" -Force -ErrorAction SilentlyContinue
}

$netDir = "$dst\Default\Network"
if (!(Test-Path $netDir)) {
    New-Item -ItemType Directory -Path $netDir -Force | Out-Null
}

$cookieSrc = "$src\Default\Network\Cookies"
$cookieDst = "$dst\Default\Network\Cookies"

$copied = $false

if (Test-Path $cookieSrc) {
    try {
        Copy-Item -Path $cookieSrc -Destination $cookieDst -Force -ErrorAction Stop
        $copied = $true
    } catch {
        # Edge background lock detected -> gracefully release lock
        Write-Host "Closing background Edge processes to release lock..."
        Stop-Process -Name msedge -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 1500
        try {
            Copy-Item -Path $cookieSrc -Destination $cookieDst -Force -ErrorAction Stop
            $copied = $true
        } catch {
            Write-Host "COOKIE_COPY_FAILED: $($_.Exception.Message)"
        }
    }
}

if ($copied) {
    Write-Host "COPIED_COOKIES_SUCCESS: $(Get-Item $cookieDst | Select-Object -ExpandProperty Length) bytes"
}
