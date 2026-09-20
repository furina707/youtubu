# -*- coding: utf-8 -*-
"""基于 Python 标准库 tkinter 的实时双字幕控制面板。
零外部 GUI 依赖，开箱即用。
"""

from __future__ import annotations

import sys
import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

from .languages import code_list
from .capture import list_inputs
from .ui_tk_overlay import TkSubtitleOverlay


class TkLivePanel(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("实时双字幕（标准库 Tkinter 版）")
        self.geometry("560x520")
        self.minsize(480, 440)

        self.engine = None
        self.overlay: Optional[TkSubtitleOverlay] = None
        self._inputs = []
        self._msg_queue = queue.Queue()

        self._build_ui()
        self.refresh_inputs()

        # 启动定时轮询，处理后台子线程发送给 GUI 的消息和电平刷新
        self.after(100, self._process_queue)
        self.after(300, self._update_level)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        # 整体采用扁平优雅现代风格
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        padding_opts = {"padx": 10, "pady": 5}

        # ---- 1. 输入源分组 ----
        input_group = ttk.LabelFrame(self, text="输入源（捕获系统正在播放的声音，或麦克风）", padding=10)
        input_group.pack(fill=tk.X, padx=12, pady=(10, 5))

        row1 = ttk.Frame(input_group)
        row1.pack(fill=tk.X)

        self.input_var = tk.StringVar()
        self.input_combo = ttk.Combobox(row1, textvariable=self.input_var, state="readonly")
        self.input_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        refresh_btn = ttk.Button(row1, text="刷新设备", command=self.refresh_inputs)
        refresh_btn.pack(side=tk.RIGHT)

        self.level_label = ttk.Label(input_group, text="输入电平: —")
        self.level_label.pack(anchor=tk.W, pady=(6, 0))

        # ---- 2. 语言与模型配置分组 ----
        cfg_group = ttk.LabelFrame(self, text="语言与模型配置", padding=10)
        cfg_group.pack(fill=tk.X, padx=12, pady=5)

        cfg_cols = ttk.Frame(cfg_group)
        cfg_cols.pack(fill=tk.X)

        # 源语言
        col1 = ttk.Frame(cfg_cols)
        col1.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Label(col1, text="源语言:").pack(anchor=tk.W)
        self.src_var = tk.StringVar()
        self.src_combo = ttk.Combobox(col1, textvariable=self.src_var, state="readonly")
        self.src_combo.pack(fill=tk.X)

        # 目标语言
        col2 = ttk.Frame(cfg_cols)
        col2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Label(col2, text="目标语言:").pack(anchor=tk.W)
        self.tgt_var = tk.StringVar()
        self.tgt_combo = ttk.Combobox(col2, textvariable=self.tgt_var, state="readonly")
        self.tgt_combo.pack(fill=tk.X)

        # 转写模型
        col3 = ttk.Frame(cfg_cols)
        col3.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        ttk.Label(col3, text="转写模型:").pack(anchor=tk.W)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            col3, textvariable=self.model_var, state="readonly",
            values=["whisper-tiny", "whisper-base", "whisper-small", "whisper-medium", "whisper-large-v3"]
        )
        self.model_combo.current(0)  # 默认 tiny 速度最快
        self.model_combo.pack(fill=tk.X)

        # 填充语言列表
        lang_items = code_list()
        self._lang_codes = [c for c, _ in lang_items]
        self._lang_names = [n for _, n in lang_items]
        self.src_combo["values"] = self._lang_names
        self.tgt_combo["values"] = self._lang_names

        self.src_combo.current(0)  # 英文
        # 默认中文
        zh_idx = self._lang_codes.index("zh") if "zh" in self._lang_codes else 1
        self.tgt_combo.current(zh_idx)

        # ---- 3. 控制操作区 ----
        ctrl_frame = ttk.Frame(self, padding=5)
        ctrl_frame.pack(fill=tk.X, padx=12, pady=5)

        self.start_btn = tk.Button(
            ctrl_frame, text="▶ 开始实时字幕", font=("Microsoft YaHei", 10, "bold"),
            bg="#2e7d32", fg="#ffffff", activebackground="#1b5e20", activeforeground="#ffffff",
            relief=tk.FLAT, padx=12, pady=6, command=self.on_start
        )
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.stop_btn = tk.Button(
            ctrl_frame, text="⏹ 停止", font=("Microsoft YaHei", 10),
            bg="#c62828", fg="#ffffff", activebackground="#8e0000", activeforeground="#ffffff",
            relief=tk.FLAT, padx=12, pady=6, state=tk.DISABLED, command=self.on_stop
        )
        self.stop_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.overlay_var = tk.BooleanVar(value=True)
        self.overlay_chk = ttk.Checkbutton(
            self, text="显示独立置顶悬浮字幕窗口", variable=self.overlay_var,
            command=self._on_overlay_chk_toggled
        )
        self.overlay_chk.pack(anchor=tk.W, padx=16, pady=2)

        # ---- 4. 运行日志与实时字幕预览区 ----
        log_group = ttk.LabelFrame(self, text="识别与翻译日志", padding=6)
        log_group.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 10))

        self.log_text = tk.Text(log_group, wrap=tk.WORD, font=("Consolas", 9), relief=tk.SOLID, bd=1)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_group, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    # ---- 设备枚举与异步加载 ----
    def refresh_inputs(self):
        self.input_combo["values"] = ["（正在扫描输入设备…）"]
        self.input_combo.current(0)

        def worker():
            try:
                items = list_inputs()
            except Exception as e:
                self._post_msg("log", f"扫描输入设备失败: {e}")
                items = []
            self._post_msg("inputs", items)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_inputs(self, items: list):
        self._inputs = items
        labels = [it["label"] for it in items]
        if not labels:
            labels = ["（未找到输入设备）"]
        self.input_combo["values"] = labels
        self.input_combo.current(0)
        self._append_log(f"可用音频输入源：{len(self._inputs)} 个")

    def selected_input(self):
        idx = self.input_combo.current()
        if 0 <= idx < len(self._inputs):
            return self._inputs[idx]
        return None

    # ---- 悬浮窗联动 ----
    def _ensure_overlay(self):
        if self.overlay is None or not self.overlay.winfo_exists():
            self.overlay = TkSubtitleOverlay(master=self, on_close=self._on_overlay_closed)
        return self.overlay

    def _on_overlay_closed(self):
        self.overlay_var.set(False)

    def _on_overlay_chk_toggled(self):
        if self.overlay_var.get():
            ol = self._ensure_overlay()
            ol.deiconify()
        else:
            if self.overlay and self.overlay.winfo_exists():
                self.overlay.withdraw()

    # ---- 开始 / 停止控制 ----
    def on_start(self):
        dev = self.selected_input()
        if dev is None:
            messagebox.showwarning("提示", "未找到可用的音频输入设备，请检查系统设置！")
            return

        src_code = self._lang_codes[self.src_combo.current()]
        tgt_code = self._lang_codes[self.tgt_combo.current()]
        model_name = self.model_var.get().replace("whisper-", "")

        if self.overlay_var.get():
            ol = self._ensure_overlay()
            ol.deiconify()

        try:
            from .live import LiveEngine
            self.engine = LiveEngine(
                input_device=dev["id"],
                source_iso=src_code,
                target_iso=tgt_code,
                asr_model=model_name,
                on_update=lambda state: self._post_msg("subtitle", state),
                on_log=lambda msg: self._post_msg("log", msg),
            )
            self.engine.start()
        except ImportError as exc:
            messagebox.showerror(
                "缺少依赖",
                f"启动实时识别失败，当前 Python 环境缺少必要依赖：\n{exc}\n\n请在命令行运行：\npip install soundcard numpy faster-whisper transformers torch"
            )
            return
        except Exception as exc:
            messagebox.showerror("启动失败", f"启动实时字幕引擎失败：\n{exc}")
            return

        self.start_btn.config(state=tk.DISABLED, bg="#9e9e9e")
        self.stop_btn.config(state=tk.NORMAL, bg="#c62828")
        self._append_log(f"正在监听：{dev['label']} | {src_code} → {tgt_code} | 模型: {model_name}")

    def on_stop(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.start_btn.config(state=tk.NORMAL, bg="#2e7d32")
        self.stop_btn.config(state=tk.DISABLED, bg="#9e9e9e")
        self.level_label.config(text="输入电平: —")

    # ---- 线程间安全通信与 UI 更新 ----
    def _post_msg(self, mtype: str, data):
        self._msg_queue.put((mtype, data))

    def _process_queue(self):
        try:
            while not self._msg_queue.empty():
                mtype, data = self._msg_queue.get_nowait()
                if mtype == "inputs":
                    self._apply_inputs(data)
                elif mtype == "log":
                    self._append_log(data)
                elif mtype == "subtitle":
                    if self.overlay and self.overlay.winfo_exists() and self.overlay_var.get():
                        self.overlay.set_subtitle(data.get("src", ""), data.get("tgt", ""))
                    self.level_label.config(text=f"输入电平: —（已出字幕 {data.get('count', 0)} 条）")
        except Exception:
            pass
        finally:
            self.after(80, self._process_queue)

    def _update_level(self):
        if self.engine and self.engine.running():
            lv = getattr(self.engine.capture, "level", 0.0)
            txt = f"输入电平: {lv:.3f}"
            if lv > 0.02:
                txt += "  🔊 有声"
            self.level_label.config(text=txt)
        self.after(350, self._update_level)

    def _append_log(self, text: str):
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)

    def on_close(self):
        self.on_stop()
        if self.overlay and self.overlay.winfo_exists():
            self.overlay.destroy()
        self.destroy()


def run():
    app = TkLivePanel()
    app.mainloop()


if __name__ == "__main__":
    run()
