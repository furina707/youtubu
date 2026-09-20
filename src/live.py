# -*- coding: utf-8 -*-
"""实时双字幕引擎：持续捕获声音 -> whisper 流式转写 -> NLLB 翻译 -> 发布当前字幕。

采用滑窗增量转写：每隔 intervalRe passing 对最近窗口转写一次，仅发布
“时间轴上未处理过的新句子”，并在回调里给出当前 (原文, 译文) 与历史记录。
"""

from __future__ import annotations

import threading
import time

from .capture import AudioCapture
from .asr import LocalASR
from .translate import LocalTranslator


class LiveEngine:
    def __init__(self, input_device, source_iso: str, target_iso: str,
                 asr_model: str = "small",
                 window_sec: float = 8.0,
                 interval: float = 2.5,
                 on_update=None,        # callable(state) 当前字幕更新
                 on_log=None):          # callable(str)
        self.capture = AudioCapture(input_device, window_sec=30.0)
        self.asr = LocalASR(model_size=asr_model)
        self.translator = LocalTranslator()
        self.source_iso = source_iso
        self.target_iso = target_iso
        self.window_sec = window_sec
        self.interval = interval
        self.on_update = on_update
        self.on_log = on_log
        self._run = False
        self._thread = None
        self._latest_end = 0.0      # 已处理到的音频时间点
        self._lock = threading.Lock()
        self._pub_count = 0

    # ---- 状态 ----
    def _log(self, m):
        if self.on_log:
            try: self.on_log(m)
            except Exception: pass

    def _publish(self, src: str, tgt: str):
        self._pub_count += 1
        state = {
            "src": src,
            "tgt": tgt,
            "count": self._pub_count,
            "time": time.time(),
        }
        if self.on_update:
            try: self.on_update(state)
            except Exception: pass

    # ---- 控制 ----
    def start(self):
        self._run = True
        self.capture.start()
        self._log(f"开始实时捕获：{self._input_label()}")
        self._log(f"源语言={self.source_iso} → 目标语言={self.target_iso}，窗口={int(self.window_sec)}s")
        try:
            self.asr._load()
            self._log(f"转写模型 {self.asr.model_size} 就绪")
        except Exception as e:
            self._log(f"转写模型加载失败: {e}")
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _input_label(self):
        return getattr(self.capture.device, "name", "输入") if hasattr(self.capture, "device") else "输入"

    def stop(self):
        self._run = False
        self.capture.stop()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._log("已停止。")

    def running(self) -> bool:
        return self._run

    # ---- 主循环 ----
    def _loop(self):
        overlap = 0.5
        history_texts: list[str] = []
        while self._run:
            t0 = time.time()
            try:
                audio, start_sec = self.capture.snapshot(self.window_sec)
                if audio.size == 0:
                    time.sleep(self.interval)
                    continue
                # whisper 滑窗转写
                segs = self.asr.transcribe_array(
                    audio,
                    language=self.asr_lang(),
                    task="transcribe",
                )
                if not segs:
                    if self.capture.level > 0.03:
                        self._log(f"电平 {self.capture.level:.3f}：本次窗口未识别到清晰语音")
                    time.sleep(self.interval)
                    continue

                # 将相对于当前切片的时间戳转换为整条时间线的绝对时间戳
                for s in segs:
                    abs_start = start_sec + s.start
                    abs_end = start_sec + s.end
                    text = s.text.strip()
                    if not text:
                        continue
                    # 过滤已发布过的句子（基于时间线进度与文本去重）
                    if abs_end <= self._latest_end - overlap:
                        continue
                    if text in history_texts[-4:]:
                        continue

                    # 达到发布标准的新句子
                    self._latest_end = max(self._latest_end, abs_end)
                    history_texts.append(text)
                    if len(history_texts) > 20:
                        history_texts.pop(0)

                    tgt = self.translator.translate(text,
                                                    self.source_iso,
                                                    self.target_iso)
                    self._publish(text, tgt)
                    self._log(f"▸ {text} → {tgt}")
            except Exception as e:
                import traceback
                self._log(f"处理错误: {e}\n{traceback.format_exc()}")
            # 维持节奏
            el = time.time() - t0
            if el < self.interval:
                time.sleep(self.interval - el)

    def asr_lang(self) -> str | None:
        """返回 whisper 语言代码（源语言）。"""
        from .languages import whisper_code
        return whisper_code(self.source_iso)
