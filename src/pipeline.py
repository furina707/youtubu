# -*- coding: utf-8 -*-
"""端到端流水线：下载 -> 转写(ASR) -> 翻译(NLLB) -> 双字幕段。"""

from __future__ import annotations

import os
import threading

from .asr import LocalASR
from .translate import LocalTranslator
from .downloader import Downloader


class Pipeline:
    def __init__(self, work_dir: str, asr_model: str = "small",
                 asr_device: str = "auto", translate_device: str = "cpu"):
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)
        self.downloader = Downloader(work_dir)
        self.asr = LocalASR(model_size=asr_model, device=asr_device)
        self.translator = LocalTranslator(device=translate_device)
        self._stop = threading.Event()
        self.status_cb = None  # callable(str)

    def log(self, msg: str):
        if self.status_cb:
            self.status_cb(msg)

    def run(self, url: str, source_iso: str, target_iso: str,
            keep_audio: bool = True, quality: str = "best",
            cookies_from_browser: str | None = None) -> dict:
        """执行完整流程，返回 {video, segments, source, target, title}。"""
        self._stop.clear()
        self.log(f"下载视频（画质: {quality}）…")
        dl = self.downloader.download(url, progress=self._dl_progress, quality=quality,
                                      cookies_from_browser=cookies_from_browser)
        self.log("抽取音轨…")
        # (download 内已抽取 audio)
        audio = dl["audio"]

        self.log("本地模型转写中（首次会下载模型，之后离线）…")
        from .languages import whisper_code
        asr_lang = whisper_code(source_iso)
        segments = self.asr.transcribe(audio, language=asr_lang)
        self.log(f"转写完成，共 {len(segments)} 句，开始翻译…")

        texts = [s.text for s in segments]
        # 首次调用会加载/下载 NLLB 翻译模型
        self.log("加载离线翻译模型（首次会下载）…")
        translated = self.translator.translate_batch(
            texts, source_iso, target_iso, batch_size=8)
        for seg, tr in zip(segments, translated):
            seg.translated = tr

        self.log("完成。")
        return {
            "video": dl["video"],
            "audio": audio,
            "segments": segments,
            "source": source_iso,
            "target": target_iso,
            "title": dl["title"],
        }

    def _dl_progress(self, d):
        status = d.get("status")
        if status == "downloading":
            pct = d.get("_percent_str", "").strip()
            self.log(f"下载中 {pct}")
        elif status == "finished":
            self.log("下载完成，合并中…")

    def cancel(self):
        self._stop.set()
        self.log("已请求取消。")
