@echo off
title Ent Organizer - Movies ^& TV Wizard
echo ===================================================
echo   Starting Ent Organizer - Movies ^& TV Wizard...
echo ===================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Install Python 3.9+ from python.org or the Microsoft Store.
    pause
    exit /b
)

python "%~dp0gui.py" %*
pause
