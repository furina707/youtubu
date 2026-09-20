@echo off
chcp 65001 >nul
title youtubu - Web 浏览器服务
cd /d "%~dp0"
if exist "%~dp0venv\Scripts\activate.bat" call "%~dp0venv\Scripts\activate.bat"
if not defined HF_ENDPOINT set HF_ENDPOINT=https://hf-mirror.com
echo ===================================================
echo   正在启动 youtubu Web 服务...
echo   启动后请在浏览器中打开: http://127.0.0.1:8000
echo ===================================================
python web.py --host 0.0.0.0 --port 8000
pause
