# -*- coding: utf-8 -*-
"""youtubu Web 服务端：提供基于浏览器的现代 WebUI 界面。

功能：
- 网页端一键提交视频链接（YouTube、抖音、B站等）
- 支持选择 Whisper 模型、源语言与目标语言、视频画质
- 任务异步执行、实时日志进度反馈
- 在线预览播放视频与双语对照字幕
- 一键下载生成的 .srt 字幕文件与音视频
"""

from __future__ import annotations

import os
import sys
import uuid
import asyncio
import threading
from typing import Dict, Any, List

# 确保项目根目录在 sys.path 中
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from fastapi import FastAPI, BackgroundTasks, HTTPException
    from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("[错误] 未安装 Web 依赖，请运行: pip install fastapi uvicorn")
    sys.exit(1)

from src.languages import LANG_MAP, code_list
from src.pipeline import Pipeline

OUTPUTS_DIR = os.path.join(ROOT, "outputs")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

app = FastAPI(title="youtubu WebUI", version="1.0.0")

# 内存中存储的任务状态
TASKS: Dict[str, Dict[str, Any]] = {}


class ProcessRequest(BaseModel):
    url: str
    src_lang: str = "en"
    tgt_lang: str = "zh"
    model_size: str = "small"
    quality: str = "best"


def run_pipeline_task(task_id: str, req: ProcessRequest):
    task = TASKS[task_id]
    task["status"] = "processing"
    task["logs"].append(f"任务启动，处理链接: {req.url}")

    def on_status(msg: str):
        task["logs"].append(msg)
        task["current_step"] = msg

    try:
        pipe = Pipeline(
            work_dir=OUTPUTS_DIR,
            asr_model=req.model_size,
        )
        pipe.status_cb = on_status

        result = pipe.run(
            url=req.url,
            source_iso=req.src_lang,
            target_iso=req.tgt_lang,
            quality=req.quality,
        )

        video_path = result.get("video")
        srt_path = ""
        if video_path and os.path.exists(video_path):
            srt_path = os.path.splitext(video_path)[0] + ".srt"
            with open(srt_path, "w", encoding="utf-8") as f:
                for idx, seg in enumerate(result["segments"], 1):
                    f.write(seg.to_srt_block(idx))

        segments_data = [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "translated": s.translated,
            }
            for s in result.get("segments", [])
        ]

        task["status"] = "completed"
        task["current_step"] = "处理完成！"
        task["video_filename"] = os.path.basename(video_path) if video_path else ""
        task["srt_filename"] = os.path.basename(srt_path) if srt_path else ""
        task["segments"] = segments_data
        task["logs"].append(f"成功导出字幕，共 {len(segments_data)} 条。")

    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["logs"].append(f"处理失败: {str(e)}")


@app.post("/api/tasks")
def create_task(req: ProcessRequest, bg: BackgroundTasks):
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="视频链接不能为空")
    
    task_id = str(uuid.uuid4())[:8]
    TASKS[task_id] = {
        "id": task_id,
        "url": req.url.strip(),
        "status": "pending",
        "current_step": "等待开始...",
        "logs": [],
        "video_filename": "",
        "srt_filename": "",
        "segments": [],
        "error": None,
    }

    # 启动后台线程执行流水线
    threading.Thread(target=run_pipeline_task, args=(task_id, req), daemon=True).start()
    return {"task_id": task_id}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TASKS[task_id]


@app.get("/api/history")
def get_history():
    files = []
    if os.path.exists(OUTPUTS_DIR):
        for f in os.listdir(OUTPUTS_DIR):
            if f.endswith((".mp4", ".mkv", ".webm", ".srt", ".wav")):
                path = os.path.join(OUTPUTS_DIR, f)
                files.append({
                    "name": f,
                    "size": os.path.getsize(path),
                    "mtime": os.path.getmtime(path),
                    "is_srt": f.endswith(".srt")
                })
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": files[:30]}


@app.get("/files/{filename}")
def download_file(filename: str):
    safe_name = os.path.basename(filename)
    path = os.path.join(OUTPUTS_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=safe_name)


# ------------------------------------------------------------------------------
# 网页前端 HTML 单页 SPA（现代响应式 Glassmorphism 设计）
# ------------------------------------------------------------------------------
INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>youtubu - Web 视频双语字幕工坊</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: rgba(18, 24, 38, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #8b5cf6;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --danger: #ef4444;
      --radius: 12px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); min-height: 100vh; padding: 24px 16px; background-image: radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.12) 0, transparent 50%), radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.1) 0, transparent 50%); }

    .container { max-width: 1080px; margin: 0 auto; }
    
    header { text-align: center; margin-bottom: 32px; }
    header h1 { font-size: 2.2rem; font-weight: 800; background: linear-gradient(135deg, #60a5fa, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 8px; }
    header p { color: var(--text-muted); font-size: 0.95rem; }

    .grid { display: grid; grid-template-columns: 1fr; gap: 24px; }
    @media (min-width: 860px) { .grid { grid-template-columns: 1.1fr 0.9fr; } }

    .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius); padding: 24px; backdrop-filter: blur(16px); box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
    .card h2 { font-size: 1.25rem; font-weight: 700; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; color: #e2e8f0; }

    .form-group { margin-bottom: 16px; }
    label { display: block; font-size: 0.85rem; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; }
    input[type="text"], select { width: 100%; padding: 12px 14px; background: rgba(0,0,0,0.35); border: 1px solid var(--card-border); border-radius: 8px; color: #fff; font-size: 0.95rem; outline: none; transition: 0.2s border-color; }
    input[type="text"]:focus, select:focus { border-color: var(--primary); }

    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

    .btn { display: inline-flex; align-items: center; justify-content: center; width: 100%; padding: 14px; background: linear-gradient(135deg, var(--primary), var(--accent)); color: white; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; transition: all 0.2s ease; margin-top: 8px; }
    .btn:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(59,130,246,0.35); }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }

    .log-box { background: rgba(0,0,0,0.5); border-radius: 8px; padding: 14px; height: 180px; overflow-y: auto; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 0.85rem; line-height: 1.6; border: 1px solid rgba(255,255,255,0.05); }
    .log-item { color: #cbd5e1; }
    .log-item.error { color: var(--danger); font-weight: bold; }

    .status-badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 12px; }
    .status-pending { background: #374151; color: #9ca3af; }
    .status-processing { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }
    .status-completed { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); }
    .status-failed { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); }

    .download-btns { display: flex; gap: 10px; margin-top: 14px; }
    .download-btn { flex: 1; padding: 10px; background: rgba(255,255,255,0.08); border: 1px solid var(--card-border); color: #fff; text-decoration: none; text-align: center; border-radius: 8px; font-size: 0.85rem; font-weight: 600; transition: background 0.2s; }
    .download-btn:hover { background: rgba(255,255,255,0.18); }

    .subtitles-container { max-height: 240px; overflow-y: auto; margin-top: 14px; border-radius: 8px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.05); }
    .sub-item { padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 0.85rem; }
    .sub-item:last-child { border-bottom: none; }
    .sub-time { font-size: 0.75rem; color: #64748b; font-family: monospace; }
    .sub-text { color: #94a3b8; margin: 2px 0; }
    .sub-trans { color: #f8fafc; font-weight: 500; }

    .history-list { list-style: none; max-height: 280px; overflow-y: auto; }
    .history-item { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.04); font-size: 0.85rem; }
    .history-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 65%; color: #cbd5e1; }
    .history-dl { color: var(--primary); text-decoration: none; font-size: 0.8rem; font-weight: 600; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>✨ youtubu Web 控制台</h1>
      <p>YouTube / 抖音视频下载 · faster-whisper 本地语音识别 · 离线多语言字幕翻译</p>
    </header>

    <div class="grid">
      <!-- 左侧：任务提交表单 -->
      <div class="card">
        <h2>🚀 发起处理任务</h2>
        <div class="form-group">
          <label>视频链接 (YouTube / 抖音等)</label>
          <input type="text" id="urlInput" placeholder="https://www.youtube.com/watch?v=... 或 抖音分享链接">
        </div>

        <div class="row">
          <div class="form-group">
            <label>原声语言 (识别)</label>
            <select id="srcLang">
              <option value="en" selected>英文 / English</option>
              <option value="zh">中文(简体) / Chinese</option>
              <option value="ja">日文 / Japanese</option>
              <option value="ko">韩文 / Korean</option>
              <option value="fr">法文 / French</option>
              <option value="de">德文 / German</option>
              <option value="es">西文 / Spanish</option>
              <option value="ru">俄文 / Russian</option>
            </select>
          </div>
          <div class="form-group">
            <label>翻译目标语言</label>
            <select id="tgtLang">
              <option value="zh" selected>中文(简体) / Chinese</option>
              <option value="en">英文 / English</option>
              <option value="zh_tw">中文(繁体) / Chinese TW</option>
              <option value="ja">日文 / Japanese</option>
              <option value="ko">韩文 / Korean</option>
              <option value="fr">法文 / French</option>
              <option value="de">德文 / German</option>
              <option value="es">西文 / Spanish</option>
            </select>
          </div>
        </div>

        <div class="row">
          <div class="form-group">
            <label>Whisper 模型大小</label>
            <select id="modelSize">
              <option value="tiny">tiny (极速/低占用)</option>
              <option value="base">base (平衡)</option>
              <option value="small" selected>small (推荐)</option>
              <option value="medium">medium (高精度)</option>
              <option value="large-v3">large-v3 (专业最强)</option>
            </select>
          </div>
          <div class="form-group">
            <label>视频下载画质</label>
            <select id="quality">
              <option value="best" selected>最高画质 (Best)</option>
              <option value="1080p">1080P 高清</option>
              <option value="720p">720P 标清</option>
              <option value="audio_only">仅提取音频 (极速)</option>
            </select>
          </div>
        </div>

        <button class="btn" id="startBtn" onclick="submitTask()">开始下载并翻译</button>
      </div>

      <!-- 右侧：当前任务状态与实时日志 -->
      <div class="card">
        <h2>⚡ 实时处理状态</h2>
        <div id="statusSection" style="display: none;">
          <div><span id="taskBadge" class="status-badge status-pending">等待中</span></div>
          <p id="taskStep" style="font-size: 0.9rem; margin-bottom: 12px; color: #94a3b8;">就绪</p>
          
          <label>执行日志流</label>
          <div class="log-box" id="logBox"></div>

          <!-- 任务完成后的下载操作 -->
          <div id="resultSection" style="display: none;">
            <div class="download-btns">
              <a id="srtDl" href="#" class="download-btn" download>📥 下载 SRT 字幕</a>
              <a id="videoDl" href="#" class="download-btn" download>🎬 下载视频</a>
            </div>

            <!-- 字幕预览 -->
            <label style="margin-top: 14px;">字幕预览 (最近片段)</label>
            <div class="subtitles-container" id="subtitlesList"></div>
          </div>
        </div>

        <div id="emptyNotice" style="color: var(--text-muted); text-align: center; padding: 48px 0; font-size: 0.9rem;">
          在左侧输入视频链接并点击「开始」即可在此查看实时处理过程。
        </div>
      </div>
    </div>

    <!-- 底部：历史输出文件 -->
    <div class="card" style="margin-top: 24px;">
      <h2>📁 outputs 产物管理</h2>
      <ul class="history-list" id="historyList">
        <li style="color: var(--text-muted); font-size: 0.85rem; padding: 12px;">加载中...</li>
      </ul>
    </div>
  </div>

  <script>
    let currentTaskId = null;
    let pollInterval = null;

    async function submitTask() {
      const url = document.getElementById('urlInput').value.trim();
      if (!url) {
        alert("请输入有效的视频链接！");
        return;
      }

      const startBtn = document.getElementById('startBtn');
      startBtn.disabled = true;
      startBtn.innerText = "正在提交任务...";

      try {
        const res = await fetch('/api/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            url: url,
            src_lang: document.getElementById('srcLang').value,
            tgt_lang: document.getElementById('tgtLang').value,
            model_size: document.getElementById('modelSize').value,
            quality: document.getElementById('quality').value
          })
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "提交任务失败");
        }

        const data = await res.json();
        currentTaskId = data.task_id;

        document.getElementById('emptyNotice').style.display = 'none';
        document.getElementById('statusSection').style.display = 'block';
        document.getElementById('resultSection').style.display = 'none';
        document.getElementById('logBox').innerHTML = '';

        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(checkStatus, 1500);
        checkStatus();

      } catch (e) {
        alert("错误: " + e.message);
        startBtn.disabled = false;
        startBtn.innerText = "开始下载并翻译";
      }
    }

    async function checkStatus() {
      if (!currentTaskId) return;

      try {
        const res = await fetch('/api/tasks/' + currentTaskId);
        if (!res.ok) return;
        const task = await res.json();

        // 更新状态徽章
        const badge = document.getElementById('taskBadge');
        badge.className = 'status-badge status-' + task.status;
        badge.innerText = task.status;

        document.getElementById('taskStep').innerText = task.current_step || '';

        // 更新日志
        const logBox = document.getElementById('logBox');
        logBox.innerHTML = (task.logs || []).map(l => `<div class="log-item">${escapeHtml(l)}</div>`).join('');
        logBox.scrollTop = logBox.scrollHeight;

        if (task.status === 'completed') {
          clearInterval(pollInterval);
          document.getElementById('startBtn').disabled = false;
          document.getElementById('startBtn').innerText = "开始下载并翻译";
          
          document.getElementById('resultSection').style.display = 'block';
          if (task.srt_filename) {
            document.getElementById('srtDl').href = '/files/' + encodeURIComponent(task.srt_filename);
            document.getElementById('srtDl').style.display = 'block';
          }
          if (task.video_filename) {
            document.getElementById('videoDl').href = '/files/' + encodeURIComponent(task.video_filename);
            document.getElementById('videoDl').style.display = 'block';
          }

          // 渲染字幕预览
          const subList = document.getElementById('subtitlesList');
          subList.innerHTML = (task.segments || []).slice(0, 30).map(s => `
            <div class="sub-item">
              <div class="sub-time">${formatTime(s.start)} -> ${formatTime(s.end)}</div>
              <div class="sub-text">${escapeHtml(s.text)}</div>
              <div class="sub-trans">${escapeHtml(s.translated)}</div>
            </div>
          `).join('');

          loadHistory();
        } else if (task.status === 'failed') {
          clearInterval(pollInterval);
          document.getElementById('startBtn').disabled = false;
          document.getElementById('startBtn').innerText = "开始下载并翻译";
        }
      } catch (err) {
        console.error(err);
      }
    }

    async function loadHistory() {
      try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const list = document.getElementById('historyList');
        if (!data.files || data.files.length === 0) {
          list.innerHTML = '<li style="color: var(--text-muted); font-size: 0.85rem; padding: 12px;">暂无历史文件</li>';
          return;
        }
        list.innerHTML = data.files.map(f => `
          <li class="history-item">
            <span class="history-name" title="${escapeHtml(f.name)}">${f.is_srt ? '📝 ' : '🎬 '} ${escapeHtml(f.name)}</span>
            <a class="history-dl" href="/files/${encodeURIComponent(f.name)}" download>下载 (${(f.size/1024/1024).toFixed(1)} MB)</a>
          </li>
        `).join('');
      } catch (e) {}
    }

    function formatTime(sec) {
      const s = Math.floor(sec % 60);
      const m = Math.floor((sec / 60) % 60);
      return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }

    function escapeHtml(text) {
      if (!text) return '';
      return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    loadHistory();
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


def run_web(host: str = "0.0.0.0", port: int = 8000):
    print("=" * 60)
    print("  youtubu Web 服务启动中...")
    print(f"  本地访问地址: http://127.0.0.1:{port}")
    print(f"  局域网/公网监听: http://{host}:{port}")
    print("=" * 60)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="启动 youtubu Web 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认 8000)")
    args = parser.parse_args()
    run_web(host=args.host, port=args.port)
