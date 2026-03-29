@echo off
title SymHiveLink Launcher

echo ============================================================
echo  SymHiveLink - Starting...
echo ============================================================

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
)

:: Activate virtual environment
call .venv\Scripts\activate

:: Install/update dependencies quietly
echo Checking dependencies...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

:: Launch SymHiveLink
echo Launching SymHiveLink...
echo ============================================================
python src/main.py