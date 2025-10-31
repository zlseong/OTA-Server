@echo off
REM OTA Server Startup Script (Windows)

echo ==========================================
echo OTA Server Startup
echo ==========================================

REM Check Python version
python --version
if %errorlevel% neq 0 (
    echo Error: Python not found
    exit /b 1
)

REM Check OpenSSL version
openssl version
if %errorlevel% neq 0 (
    echo Warning: OpenSSL not found
)

REM Check if virtual environment exists
if not exist "venv\" (
    echo.
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install/Update dependencies
echo.
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

REM Check configuration
if not exist "config\server.yaml" (
    echo.
    echo Warning: config\server.yaml not found
    echo Using config\server.yaml.example
    
    if not exist "config\server.yaml.example" (
        echo Error: config\server.yaml.example not found
        exit /b 1
    )
)

REM Create necessary directories
echo.
echo Creating directories...
if not exist "logs\" mkdir logs
if not exist "packages\" mkdir packages
if not exist "temp\" mkdir temp

echo.
echo ==========================================
echo Starting OTA Server...
echo ==========================================
echo.

REM Run server
python -m server.main

REM Deactivate on exit
call venv\Scripts\deactivate.bat

