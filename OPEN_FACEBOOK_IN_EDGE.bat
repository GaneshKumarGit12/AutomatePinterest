@echo off
setlocal
title Open Facebook for AutomatePinterest
set "SESSION_DIR=%~dp0user_data\automation_session"

echo ======================================================================
echo           AutomatePinterest - Facebook Session Helper
echo ======================================================================
echo.
echo [1/3] Closing any orphaned automation browser processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*automation_session*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [2/3] Cleaning Chromium singleton locks...
del /f /q "%SESSION_DIR%\SingletonLock" 2>nul
del /f /q "%SESSION_DIR%\SingletonCookie" 2>nul
del /f /q "%SESSION_DIR%\SingletonSocket" 2>nul
del /f /q "%SESSION_DIR%\lockfile" 2>nul

echo [3/3] Opening Microsoft Edge with AutomatePinterest profile...
set "EDGE_EXE="
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=C:\Program Files\Microsoft\Edge\Application\msedge.exe"

if "%EDGE_EXE%"=="" (
    echo [ERROR] Microsoft Edge executable not found in standard Program Files locations!
    echo Trying fallback via system PATH...
    start "" msedge.exe --new-window --user-data-dir="%SESSION_DIR%" --no-first-run --no-default-browser-check "https://www.facebook.com/"
) else (
    echo Launching Edge from: "%EDGE_EXE%"
    start "" "%EDGE_EXE%" --new-window --user-data-dir="%SESSION_DIR%" --no-first-run --no-default-browser-check "https://www.facebook.com/"
)

echo.
echo ======================================================================
echo Edge is now open! Log in or verify your Facebook session.
echo When you are done, close Edge so the automation can use the profile.
echo ======================================================================
pause
