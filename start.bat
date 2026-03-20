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
    pause & exit /b 1
)

REM Створення venv якщо не існує
if not exist "venv" (
    echo [1/3] Creating virtual environment...
    py -m venv venv
)

echo [2/3] Activating virtual environment...
call venv\Scripts\activate.bat

echo [3/3] Installing dependencies...
py -m pip install -r requirements.txt -q

echo.
echo ============================================
echo   Starting bot... Press Ctrl+C to stop
echo ============================================
echo.

py bot.py

echo.
echo Bot stopped.
pause
```

---

### 4. Оновлений `requirements.txt`
```
feedparser==6.0.11
requests==2.32.3