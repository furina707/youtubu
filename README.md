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

## 快速开始

### 1. 运行 TUI 终端模式
```bash
python tui.py
```

### 2. 运行 GUI 桌面模式
```bash
python -m src.main
```

### 3. CLI 命令行模式
```bash
python -m src.main <视频链接> --src en --tgt zh
```
