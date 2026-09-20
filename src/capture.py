# -*- coding: utf-8 -*-
"""系统音频捕获：用 soundcard 捕获「系统扬声器输出(loopback)」或「物理麦克风」。

返回 16k 单声道 float32 numpy 数组，供 faster-whisper 实时转写。
"""

from __future__ import annotations

import threading
import queue


def list_inputs() -> "list[dict]":
    """返回可用输入源列表：[{label, id, loopback}]。id 为可直接用于 soundcard 的麦克风对象。"""
    try:
        import soundcard as sc
    except ImportError:
        return [{"label": "（未安装 soundcard 库，无法枚举音频设备）", "id": None, "loopback": False}]

    items = []
    try:
        mics = sc.all_microphones(include_loopback=True)
        for m in mics:
            is_loop = ("Speaker" in m.name) or ("speaker" in m.name)
            items.append({
                "label": ("🔊 系统扬声器(正在播放的声音)" if is_loop
                          else "🎤 " + m.name),
                "id": m,
                "loopback": is_loop,
            })
    except Exception as e:
        items = []
    if not items:
        # 兜底：无麦克风/loopback
        try:
            for m in sc.all_microphones(include_loopback=True):
                items.append({"label": m.name, "id": m, "loopback": False})
        except Exception:
            items = []
    return items


class AudioCapture:
    """后台线程持续从指定麦克风/loopback 捕获 16k mono float32 音频。

    - `frames` 是最近窗口（秒）的音频 deque，供实时转写使用。
    - `level` 反映当前输入的实时能量（RMS），供 UI 电平表显示。
    """

    SAMPLE_RATE = 16000

    def __init__(self, device, window_sec: float = 30.0):
        self.device = device          # soundcard micro（对象）
        self.window_sec = window_sec
        self._run = False
        self._thread = None
        self._lock = threading.Lock()
        self._frames = []             # 累积示例（浮点）
        self.window_frames = int(self.SAMPLE_RATE * window_sec)
        self.level = 0.0              # 当前 RMS
        self.total_samples_recorded = 0  # 累计录制样本数

    def start(self):
        self._run = True
        self.total_samples_recorded = 0
        self._frames = []
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._run = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self):
        try:
            import numpy as np
            with self.device.recorder(samplerate=self.SAMPLE_RATE,
                                      blocksize=1024) as rec:
                while self._run:
                    data = rec.record(numframes=int(self.SAMPLE_RATE * 0.2))
                    if data is None or not data.size:
                        continue
                    x = np.asarray(data, dtype=np.float32)
                    if x.ndim > 1:
                        x = x.mean(axis=1)   # 混成单声道
                    x = np.ascontiguousarray(x)
                    # 电平
                    self.level = float(np.sqrt(np.mean(np.square(x))))
                    with self._lock:
                        self._frames.append(x)
                        self.total_samples_recorded += len(x)
                        # 限制窗口长度
                        total = sum(len(f) for f in self._frames)
                        while total > self.window_frames and len(self._frames) > 1:
                            dropped = self._frames.pop(0)
                            total -= len(dropped)
        except Exception as e:
            import traceback
            self.error = traceback.format_exc()
            self.level = -1.0   # 标记出错

    def snapshot(self, seconds: float = 6.0) -> tuple:
        """返回 (最近 seconds 秒音频, 该音频起始相对录音开头的秒数)。"""
        import numpy as np
        n = int(self.SAMPLE_RATE * seconds)
        with self._lock:
            frames = list(self._frames)
            current_total = self.total_samples_recorded
        if not frames:
            return np.zeros(0, dtype=np.float32), 0.0
        audio = np.concatenate(frames)
        if len(audio) > n:
            audio = audio[-n:]
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        # 计算这段音频在整条时间线上的起始绝对秒数
        start_sec = max(0.0, (current_total - len(audio)) / float(self.SAMPLE_RATE))
        return audio, start_sec

