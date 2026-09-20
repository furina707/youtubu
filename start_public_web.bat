@echo off
chcp 65001 >nul
title youtubu - 一键公网穿透访问
cd /d "%~dp0"

echo ========================================================
echo        youtubu Web 服务 + Cloudflare 公网穿透
echo ========================================================
echo.

rem 1. 查找 cloudflared 路径
set "CF_CMD=cloudflared"
where cloudflared >nul 2>nul
if %errorlevel% neq 0 (
    if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" (
        set "CF_CMD=C:\Program Files (x86)\cloudflared\cloudflared.exe"
    ) else if exist "C:\Program Files\cloudflared\cloudflared.exe" (
        set "CF_CMD=C:\Program Files\cloudflared\cloudflared.exe"
    ) else (
        echo [错误] 未检测到 cloudflared，请先运行: winget install Cloudflare.cloudflared
        pause
        exit /b 1
    )
)

rem 2. 后台启动本地 Web 服务
echo [1/2] 正在启动本地 Web 服务 (端口 8000)...
start "youtubu-Web-Backend" /min cmd /c "start_web.bat"

rem 等待 3 秒确保服务就绪
timeout /t 3 /nobreak >nul

rem 3. 启动 Cloudflare 穿透
echo [2/2] 正在开启 Cloudflare 隧道...
echo.
echo ========================================================
echo  请在下方日志中找到类似如下的公网临时链接：
echo  https://xxxxxxxx.trycloudflare.com
echo  复制到手机或外部电脑浏览器即可直接访问！
echo ========================================================
echo.

"%CF_CMD%" tunnel --url http://localhost:8000

pause
