# -*- coding: utf-8 -*-
"""基于 Python 标准库 tkinter 的悬浮置顶双字幕窗口。
无需安装 PySide6，开箱即用。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional


class TkSubtitleOverlay(tk.Toplevel):
    """置顶、无边框、可拖动的独立字幕悬浮窗（标准库 tkinter 实现）。"""

    def __init__(self, master=None, on_close: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self.on_close_callback = on_close

        self.title("实时双字幕")
        # 移除系统窗口标题栏边框
        self.overrideredirect(True)
        # 窗口置顶
        self.attributes("-topmost", True)
        self._pinned = True

        # 设置背景深色微透明（Windows 支持 -alpha）
        try:
            self.attributes("-alpha", 0.88)
        except Exception:
            pass

        self.configure(bg="#141a20")

        # 拖动状态
        self._drag_x = 0
        self._drag_y = 0

        # 顶部工具栏
        top_bar = tk.Frame(self, bg="#141a20")
        top_bar.pack(fill=tk.X, padx=10, pady=(6, 2))

        title_lbl = tk.Label(
            top_bar, text="实时双字幕", font=("Microsoft YaHei", 9),
            fg="#90a4ae", bg="#141a20"
        )
        title_lbl.pack(side=tk.LEFT)

        close_btn = tk.Label(
            top_bar, text="✕", font=("Microsoft YaHei", 9, "bold"),
            fg="#cfd8dc", bg="#141a20", cursor="hand2", padx=4
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self.close())

        self.pin_btn = tk.Label(
            top_bar, text="📌", font=("Microsoft YaHei", 9),
            fg="#ffd54f", bg="#141a20", cursor="hand2", padx=4
        )
        self.pin_btn.pack(side=tk.RIGHT)
        self.pin_btn.bind("<Button-1>", lambda e: self.toggle_pin())

        # 字幕显示区域
        content_frame = tk.Frame(self, bg="#141a20")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))

        # 译文行（上行，黄字高亮放大）
        self.tgt_label = tk.Label(
            content_frame, text="译文（等待声音…）",
            font=("Microsoft YaHei", 14, "bold"),
            fg="#FFE066", bg="#141a20",
            wraplength=520, justify=tk.CENTER
        )
        self.tgt_label.pack(fill=tk.X, pady=(2, 2))

        # 原文行（下行，白字稍小）
        self.src_label = tk.Label(
            content_frame, text="原文",
            font=("Microsoft YaHei", 11),
            fg="#FFFFFF", bg="#141a20",
            wraplength=520, justify=tk.CENTER
        )
        self.src_label.pack(fill=tk.X, pady=(0, 2))

        # 绑定拖动事件到所有主要组件
        for widget in (self, top_bar, title_lbl, content_frame, self.tgt_label, self.src_label):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

        # 初始尺寸与位置：右下角
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w, h = 540, 110
        x = max(0, sw - w - 40)
        y = max(0, sh - h - 60)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event):
        new_x = event.x_root - self._drag_x
        new_y = event.y_root - self._drag_y
        self.geometry(f"+{new_x}+{new_y}")

    def toggle_pin(self):
        self._pinned = not self._pinned
        self.attributes("-topmost", self._pinned)
        self.pin_btn.config(fg="#ffd54f" if self._pinned else "#78909c")

    def set_subtitle(self, src: str, tgt: str):
        """更新双字幕内容并根据文本自动计算窗口换行与宽度。"""
        self.src_label.config(text=src or "")
        self.tgt_label.config(text=tgt or "")

        # 动态根据窗口尺寸调整换行宽度
        cur_w = self.winfo_width()
        wrap_w = max(360, cur_w - 40)
        self.tgt_label.config(wraplength=wrap_w)
        self.src_label.config(wraplength=wrap_w)

    def close(self):
        self.withdraw()
        if self.on_close_callback:
            try:
                self.on_close_callback()
            except Exception:
                pass
