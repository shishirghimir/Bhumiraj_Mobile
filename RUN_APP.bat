@echo off
title Bhumiraj Mobile ^& Watch House
cd /d "%~dp0"

echo ============================================================
echo   BHUMIRAJ MOBILE ^& WATCH HOUSE  -  Retail + Wholesale
echo   Chabahil-7, Kathmandu   9808773134
echo   by Netanix Labs  -  netanixctf.com
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python is not installed or not on PATH.
    echo     Install Python 3.10+ from https://python.org
    echo     Remember to tick "Add Python to PATH" during setup.
    echo.
    pause
    exit /b 1
)

echo [1/2] Checking dependencies...
python -c "import customtkinter, reportlab, PIL" >nul 2>&1
if errorlevel 1 (
    echo       Installing required packages, please wait...
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo [X] Could not install the dependencies.
        pause
        exit /b 1
    )
)
echo       OK.

echo [2/2] Starting Bhumiraj...
echo.
python main.py
if errorlevel 1 (
    echo.
    echo [X] The application closed with an error. See the message above.
    pause
)
