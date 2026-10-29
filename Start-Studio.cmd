@echo off
cd /d "%~dp0"
if exist "release\ConvoVault-Studio.exe" (
    start "" "release\ConvoVault-Studio.exe"
    exit /b
)
python -m convovault gui
if errorlevel 1 (
    echo Install Python 3.9 or newer, then try again.
    pause
)
