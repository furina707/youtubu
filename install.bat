@echo off
chcp 65001 >nul
title youtubu - Windows 一键部署
cd /d "%~dp0"

echo =======================================================
echo          youtubu Windows 一键自动部署与安装
echo =======================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"

echo.
pause
