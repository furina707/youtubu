@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0venv\Scripts\activate.bat" call "%~dp0venv\Scripts\activate.bat"
if not defined HF_ENDPOINT set HF_ENDPOINT=https://hf-mirror.com
if "%~1"=="--web" (
    python web.py --host 0.0.0.0 --port 8000
) else if "%~1"=="" (
    python tui.py
) else (
    python -m src.main %*
)

