@echo off
title Stock Research - Setup

echo ============================================
echo   Stock Research System v2.0 - Auto Setup
echo ============================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.10+
    echo Download: https://www.python.org/downloads/
    echo (Check "Add Python to PATH" during installation)
    pause
    exit /b 1
)
echo [1/4] Python detected
python --version

if not exist ".venv" (
    echo [2/4] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
) else (
    echo [2/4] Virtual environment already exists, skip
)

echo [3/4] Installing Python packages...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [ERROR] Package install failed. Check your internet connection.
    pause
    exit /b 1
)

echo [4/4] Installing browser engine (for Xueqiu)...
python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [WARNING] Browser engine install failed. Xueqiu module will be unavailable.
    echo You can retry later: python -m playwright install chromium
)

if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo.
        echo ============================================
        echo   IMPORTANT: Edit .env file with your API Keys
        echo ============================================
        echo.
        echo Open .env with Notepad and replace:
        echo   DEEPSEEK_API_KEY=your-key     (Required)
        echo   TAVILY_API_KEY=your-key       (Required)
        echo.
        echo Get keys at:
        echo   https://platform.deepseek.com
        echo   https://tavily.com
        echo ============================================
        echo.
        start notepad .env
    )
)

echo.
echo ============================================
echo   Setup complete!
echo   Double-click run.bat to start
echo ============================================
pause
