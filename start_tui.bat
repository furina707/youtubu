@echo off
chcp 65001 >nul
title youtubu - 终端交互面板
cd /d "%~dp0"
if exist "%~dp0venv\Scripts\activate.bat" call "%~dp0venv\Scripts\activate.bat"
if not defined HF_ENDPOINT set HF_ENDPOINT=https://hf-mirror.com
python tui.py
pause
