# -*- coding: utf-8 -*-
"""本地语音识别（whisper，离线）：把音频转成带时间戳的原文字幕。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class SubtitleSegment:
    start: float          # 秒
    end: float            # 秒
    text: str             # 原文
    translated: str = ""  # 译文（由翻译模块填充）

    def to_srt_block(self, index: int):
        def fmt(t: float) -> str:
            ms = int(round((t - int(t)) * 1000))
            s = int(t)
            h, m = divmod(s, 3600)
            m, s = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        return (f"{index}\n{fmt(self.start)} --> {fmt(self.end)}\n"
                f"{self.text}\n{self.translated}\n")


class LocalASR:
    """faster-whisper 封装，自动从 HuggingFace 下载模型并缓存。”

    模型可离线使用；`model_size` 越大越准也越慢/越占内存。
    """

    def __init__(self, model_size: str = "small",
                 device: str = "auto",
                 compute_type: str = "int8",
                 model_dir: str | None = None):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model_dir = model_dir  # None => 默认 HF 缓存
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size.lower(),
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.model_dir,
            )
        return self._model

    def transcribe(self, audio_path: str, language: str | None = None,
                   task: str = "transcribe") -> list[SubtitleSegment]:
        """转写音频文件，返回带时间戳的分句列表。

        language: whisper 语言代码，None 表示自动检测。
        """
        model = self._load()
        seg_iter, info = model.transcribe(
            audio_path,
            language=language,
            task=task,
            word_timestamps=True,
            # 不强制 VAD 过滤，避免把唱歌/连续语音当成非语音丢弃
            vad_filter=False,
        )
        segments: list[SubtitleSegment] = []
        for s in seg_iter:
            text = (s.text or "").strip()
            if not text:
                continue
            segments.append(SubtitleSegment(s.start, s.end, text))
        return segments

    def transcribe_array(self, audio, language: str | None = None,
                         task: str = "transcribe") -> list[SubtitleSegment]:
        """转写一段 numpy 音频数组（16k mono float32），用于实时流式。

        返回带时间戳的分句列表。
        """
        model = self._load()
        seg_iter, info = model.transcribe(
            audio,
            language=language,
            task=task,
            word_timestamps=True,
            vad_filter=False,
        )
        segments: list[SubtitleSegment] = []
        for s in seg_iter:
            text = (s.text or "").strip()
            if not text:
                continue
            segments.append(SubtitleSegment(s.start, s.end, text))
        return segments
