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

## 一键部署（Linux / macOS 服务器）

在服务器终端直接执行以下命令，全自动完成依赖安装与部署配置：

```bash
curl -fsSL https://raw.githubusercontent.com/furina707/youtubu/main/install.sh | bash
```

> **自动特性**：
> - 自动检测并安装系统依赖（`ffmpeg`, `git`, `python3` 等）
> - 自动检测 NVIDIA GPU 硬件并配置 CUDA 12 驱动优化
> - 针对国内网络自动配置 PyPI 与 HuggingFace 镜像加速
> - 自动生成开箱即用的 `./run.sh` 启动脚本及全局 `youtubu` 命令

---

## 快速开始

### 1. 运行 TUI 终端模式
```bash
python tui.py
# 或服务器部署后直接运行：
./run.sh
```

### 2. 运行 GUI 桌面模式
```bash
python -m src.main
```

### 3. CLI 命令行模式
```bash
python -m src.main <视频链接> --src en --tgt zh
```
