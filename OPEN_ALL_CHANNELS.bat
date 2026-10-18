@echo off
setlocal
title Social Channel Session Launcher - AutomatePinterest

:MENU
cls
echo ======================================================================
echo           AutomatePinterest - Social Channel Session Manager
echo ======================================================================
echo.
echo Select which account session you want to open in Microsoft Edge:
echo.
echo   [1] Facebook (Main Profile, WorldNewzs Page, LatestNews Page, Affiliate Group)
echo   [2] Instagram (@ganeshkumard12)
echo   [3] Threads (@ganeshkumard12)
echo   [4] Open All Social Sessions Sequentially
echo   [5] Exit
echo.
set /p "CHOICE=Enter choice [1-5]: "

if "%CHOICE%"=="1" goto FB
if "%CHOICE%"=="2" goto INSTA
if "%CHOICE%"=="3" goto THREADS
if "%CHOICE%"=="4" goto ALL
if "%CHOICE%"=="5" goto EXIT
goto MENU

:FB
call "%~dp0OPEN_FACEBOOK_IN_EDGE.bat"
goto MENU

:INSTA
call "%~dp0OPEN_INSTAGRAM_SESSION.bat"
goto MENU

:THREADS
call "%~dp0OPEN_THREADS_SESSION.bat"
goto MENU

:ALL
echo Opening Facebook...
call "%~dp0OPEN_FACEBOOK_IN_EDGE.bat"
echo Opening Instagram...
call "%~dp0OPEN_INSTAGRAM_SESSION.bat"
echo Opening Threads...
call "%~dp0OPEN_THREADS_SESSION.bat"
goto MENU

:EXIT
exit /b 0
