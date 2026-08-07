@echo off
title Building Bhumiraj EXE
cd /d "%~dp0"

echo ============================================================
echo   BUILDING  -  Bhumiraj Mobile ^& Watch House
echo   Retail + Wholesale   ^|   by Netanix Labs
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python is not installed or not on PATH.
    pause
    exit /b 1
)

echo [1/4] Installing dependencies and PyInstaller...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
python -m pip install --quiet pyinstaller
if errorlevel 1 (
    echo [X] Could not install the build tools.
    pause
    exit /b 1
)

echo [2/4] Running the test suite ^(a broken build helps nobody^)...
python run_tests.py > test_output.txt 2>&1
if errorlevel 1 (
    echo [X] Tests FAILED - the build was stopped.
    echo     See test_output.txt for what went wrong.
    pause
    exit /b 1
)
echo       All tests passed.

echo [3/4] Cleaning the previous build...
if exist "build\Bhumiraj" rmdir /s /q "build\Bhumiraj"
if exist "dist\Bhumiraj"  rmdir /s /q "dist\Bhumiraj"

echo [4/4] Building the EXE ^(this takes a few minutes^)...
python -m PyInstaller --clean --noconfirm Bhumiraj.spec
if errorlevel 1 (
    echo.
    echo [X] BUILD FAILED - see the messages above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD SUCCEEDED
echo ============================================================
echo.
echo   Output folder:  dist\Bhumiraj\
echo   Run it with:    dist\Bhumiraj\Bhumiraj.exe
echo.
echo   Give the shop the WHOLE "dist\Bhumiraj" folder, not just the
echo   .exe - the data folder is created next to it, so the database
echo   travels with the app.
echo.
echo   First login:  admin  /  Admin@123
echo   You will be forced to set your own password straight away.
echo.
pause
