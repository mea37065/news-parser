@echo off
title News AI Parser Bot
cd /d "%~dp0"

echo ============================================
echo   News AI Parser Bot
echo ============================================
echo.

REM Перевірка Python
py --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

REM Створення venv якщо не існує
if not exist "venv" (
    echo [1/3] Creating virtual environment...
    py -m venv venv
    echo Done.
)

REM Активація venv
echo [2/3] Activating virtual environment...
call venv\Scripts\activate.bat

REM Встановлення залежностей
echo [3/3] Installing dependencies...
py -m pip install -r requirements.txt -q

REM Перевірка .env файлу
if not exist ".env" (
    echo.
    echo [WARNING] .env file not found!
    echo Please create .env file based on .env.example
    echo.
    copy .env.example .env
    echo .env file created. Fill in your credentials and restart.
    notepad .env
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Starting bot... Press Ctrl+C to stop
echo ============================================
echo.

py bot.py

echo.
echo Bot stopped.
pause