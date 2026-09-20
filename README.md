# youtubu

音视频下载、本地语音识别（ASR）与双语字幕翻译工具，支持 YouTube/抖音等多平台视频处理与实时桌面字幕 Overlay。

## 功能特性

- **多平台视频下载**：基于 yt-dlp 支持 YouTube、抖音等平台的视频音轨抓取。抖音视频支持自动免登录动态获取并维护 `ttwid` cookie。
- **本地语音识别（ASR）**：基于 `faster-whisper` 实现高精度、低延迟的音频转文字。
- **离线多语言翻译**：基于 HuggingFace 模型（如 NLLB 等）实现多语种翻译，生成双语对照字幕。
- **多样化交互模式**：
  - **TUI 界面**：直接运行 `python tui.py` 开启终端交互式下载与翻译面板。
  - **GUI 界面**：运行 `python -m src.main` 开启图形界面。
  - **实时桌面字幕**：支持系统音频/扬声器捕获及实时悬浮字幕叠加（Overlay）。
  - **命令行模式**：支持一键执行下载、转写、翻译和导出 SRT。

## 一键部署

### 🐧 Linux / macOS 服务器

在终端执行以下命令：
```bash
curl -fsSL https://raw.githubusercontent.com/furina707/youtubu/main/install.sh | bash
```

### 🪟 Windows 系统

在 **PowerShell** 窗口中直接执行以下一行命令即可自动完成部署：
```powershell
irm https://raw.githubusercontent.com/furina707/youtubu/main/install.ps1 | iex
```

> **或者通过批处理运行**：克隆仓库后直接双击 `install.bat`。
>
> **一键部署特性**：
> - 自动检测 Python、Git 环境（未安装时引导或通过 winget 自动安装）
> - 自动检测 NVIDIA GPU 硬件并配置 CUDA 12 驱动优化
> - 针对国内网络自动配置 PyPI 与 HuggingFace 镜像加速
> - 自动创建桌面端双击启动脚本：`start_web.bat`（Web服务）、`start_tui.bat`（终端模式）、`start_gui.bat`（桌面图形模式）

---

## 快速开始

### 1. 运行 Web 浏览器服务（推荐，支持公网/手机访问）
```bash
# Linux / macOS
./run.sh --web

# Windows
.\run.bat --web   # 或直接双击 start_web.bat
```
打开浏览器访问：`http://localhost:8000`

### 2. 运行 TUI 终端模式
```bash
python tui.py
# 或部署后直接运行：
./run.sh
```

### 3. 运行 GUI 桌面模式 (Windows)
双击 `start_gui.bat` 或运行：
```bash
python -m src.main
```

### 4. CLI 命令行模式
```bash
./run.sh <视频链接> --src en --tgt zh
```

---

## 🌐 如何通过公网在浏览器访问

### 方案 A：云服务器（有公网 IP）
1. 启动 Web 服务：`./run.sh --web`（默认监听 `0.0.0.0:8000`）。
2. 在云厂商控制台（阿里云/腾讯云等）的「安全组」中，添加一条入方向规则，**放行 8000 端口**。
3. 打开任意电脑或手机浏览器，直接访问：`http://<服务器公网IP>:8000`。

### 方案 B：本地电脑 / 无公网 IP（使用免费 Cloudflare Tunnel）
无需购买云服务器与公网 IP，自带免费 HTTPS 域名：
```bash
# 1. 启动本地 Web 服务
./run.sh --web

# 2. 运行 Cloudflare 穿透（免注册即用）
cloudflared tunnel --url http://localhost:8000
```
终端会输出一个临时的公网地址（形如 `https://xxxx.trycloudflare.com`），直接在任何地方的浏览器打开即可访问！

