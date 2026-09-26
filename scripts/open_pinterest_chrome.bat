@echo off
echo ===================================================
echo Opening Google Chrome for Pinterest Login...
echo Profile Directory: %~dp0..\user_data\pinterest_profile
echo ===================================================
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%~dp0..\user_data\pinterest_profile" "https://www.pinterest.com/login"
