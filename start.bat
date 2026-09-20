@echo off
chcp 65001 >nul
title youtubu - 一键部署与启动向导
cd /d "%~dp0"

echo ========================================================
echo          youtubu 跨平台自动检测与启动中心
echo ========================================================
echo.

rem 1. 自动检测 Windows 环境下是否已部署虚拟环境与依赖
if not exist "%~dp0venv\Scripts\python.exe" (
    echo [检测] 未检测到已配置的 Python 虚拟环境，正在自动进行一键部署...
    echo.
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
    exit /b
)

rem 2. 如果已安装，提供启动菜单（默认自动启动 WebUI）
echo [检测] 环境已就绪！
echo.
echo 请选择运行模式 (5秒无操作将默认启动 [1] Web 浏览器模式):
echo --------------------------------------------------------
echo  [1] 启动 Web 浏览器控制台 (推荐，支持电脑/手机局域网访问)
echo  [2] 启动 Web 服务 + Cloudflare 公网安全穿透 (生成外网公网链接)
echo  [3] 启动 TUI 终端全键盘控制面板
echo  [4] 启动 GUI 桌面图形客户端 (本地视频播放与双字幕)
echo  [5] 重新安装/更新项目依赖
echo --------------------------------------------------------
echo.

choice /C 12345 /T 5 /D 1 /M "请选择 [1-5]: "
set "MODE=%errorlevel%"

if "%MODE%"=="1" (
    echo.
    echo 正在唤起浏览器并启动 Web 服务...
    start http://127.0.0.1:8000
    call "%~dp0start_web.bat"
) else if "%MODE%"=="2" (
    call "%~dp0start_public_web.bat"
) else if "%MODE%"=="3" (
    call "%~dp0start_tui.bat"
) else if "%MODE%"=="4" (
    call "%~dp0start_gui.bat"
) else if "%MODE%"=="5" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
)

pause
