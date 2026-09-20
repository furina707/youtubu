@echo off
chcp 65001 >nul
title youtubu - 桌面主程序
cd /d "%~dp0"
if exist "%~dp0venv\Scripts\activate.bat" call "%~dp0venv\Scripts\activate.bat"
if not defined HF_ENDPOINT set HF_ENDPOINT=https://hf-mirror.com
python -m src.main
pause
