@echo off
cd /d "%~dp0"

if not exist ".env" (
    echo [ERROR] .env file not found. Run install.bat first.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo Starting Stock Research System...
echo.
echo Browser will open at http://localhost:8501
echo Press Ctrl+C to stop
echo.

start http://localhost:8501

streamlit run app.py --server.headless true
