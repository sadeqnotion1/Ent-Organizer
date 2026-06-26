@echo off
title Folder Organizer & Poster Icon Wizard
echo ===================================================
echo 🎬 Starting Folder Organizer & Poster Icon Wizard...
echo ===================================================

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.9+ from python.org or the Microsoft Store.
    pause
    exit /b
)

:: Run the GUI script
python "%~dp0gui.py" %*

pause
