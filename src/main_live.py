# -*- coding: utf-8 -*-
"""实时双字幕主入口：捕获系统/麦克风声音 -> 本地转写 -> 离线翻译 -> 悬浮双字幕。

用法：  python -m app.main_live
"""

from __future__ import annotations

import sys
import os
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTextEdit, QGroupBox, QCheckBox,
)

from .languages import code_list
from .capture import list_inputs
from .overlay import SubtitleOverlayWindow


class LivePanel(QWidget):
    # 后台线程扫描到输入设备后，经此信号回主线程填充下拉框
    inputs_ready = Signal(list)
    subtitle_received = Signal(dict)
    log_received = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("实时双字幕（捕获系统声音）")
        self.resize(520, 460)
        self.engine = None
        self.overlay = None
        self.inputs_ready.connect(self._apply_inputs)
        self.subtitle_received.connect(self._on_subtitle_gui)
        self.log_received.connect(self._log_gui)

        root = QVBoxLayout(self)

        # ---- 输入源 ----
        in_group = QGroupBox("输入源（捕获系统/扬声器播放的声音，或麦克风）")
        inlay = QVBoxLayout(in_group)
        row = QHBoxLayout()
        self.input_combo = QComboBox()
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh_inputs)
        row.addWidget(self.input_combo, 1)
        row.addWidget(refresh)
        inlay.addLayout(row)
        self.level_label = QLabel("输入电平: —")
        inlay.addWidget(self.level_label)
        root.addWidget(in_group)

        # ---- 语言 / 模型 ----
        cfg = QGroupBox("语言与模型")
        cg = QHBoxLayout()
        v1 = QVBoxLayout()
        v1.addWidget(QLabel("源语言:"))
        self.src_combo = QComboBox()
        v1.addWidget(self.src_combo)
        cg.addLayout(v1)
        v2 = QVBoxLayout()
        v2.addWidget(QLabel("目标语言:"))
        self.tgt_combo = QComboBox()
        v2.addWidget(self.tgt_combo)
        cg.addLayout(v2)
        v3 = QVBoxLayout()
        v3.addWidget(QLabel("转写模型:"))
        self.model_combo = QComboBox()
        for m in ["tiny", "base", "small", "medium", "large-v3"]:
            self.model_combo.addItem(f"whisper-{m}", m)
        self.model_combo.setCurrentIndex(0)  # 实时优先 tiny/base，速度快
        v3.addWidget(self.model_combo)
        cg.addLayout(v3)
        cfg.setLayout(cg)
        for code, name in code_list():
            self.src_combo.addItem(name, code)
            self.tgt_combo.addItem(name, code)
        self.src_combo.setCurrentIndex(0)
        self.tgt_combo.setCurrentIndex(
            [self.tgt_combo.itemData(i) for i in range(self.tgt_combo.count())].index("zh"))
        root.addWidget(cfg)

        # ---- 控制 ----
        ctrl = QHBoxLayout()
        self.start_btn = QPushButton("▶ 开始实时字幕")
        self.start_btn.setMinimumHeight(44)
        self.start_btn.clicked.connect(self.on_start)
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.on_stop)
        self.overlay_chk = QCheckBox("显示悬浮字幕窗口")
        self.overlay_chk.setChecked(True)
        self.overlay_chk.toggled.connect(self._on_overlay_chk_toggled)
        ctrl.addWidget(self.start_btn, 1)
        ctrl.addWidget(self.stop_btn)
        root.addLayout(ctrl)
        root.addWidget(self.overlay_chk)

        # ---- 日志 ----
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        root.addWidget(QLabel("日志:"))
        root.addWidget(self.log_view, 1)

        self._timer = None
        self._inputs = []
        self.refresh_inputs()

    # ---- 输入源 ----
    def refresh_inputs(self):
        """枚举输入设备。在后台线程扫描，结果经 inputs_ready 信号回主线程填充。"""
        self.input_combo.clear()
        self.input_combo.addItem("（正在扫描输入设备…）")

        def worker():
            try:
                items = list_inputs()
            except Exception as e:
                self.log_received.emit(f"扫描输入设备失败: {e}")
                items = []
            self.inputs_ready.emit(items)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_inputs(self, items: list):
        """主线程槽：用扫描结果填充下拉框。"""
        self._inputs = items
        self.input_combo.clear()
        for it in self._inputs:
            self.input_combo.addItem(it["label"])
        if not self._inputs:
            self.input_combo.addItem("（未找到输入设备）")
        self._log_gui(f"可用输入：{len(self._inputs)} 个")

    def selected_input(self):
        i = self.input_combo.currentIndex()
        if 0 <= i < len(self._inputs):
            return self._inputs[i]
        return None

    # ---- 悬浮窗联动 ----
    def _ensure_overlay(self):
        if self.overlay is None:
            self.overlay = SubtitleOverlayWindow(src_label="译文 ▏ 原文（等待识别…）",
                                                 tgt_label="译文 ▏ 原文")
            self.overlay.set_subtitle("（等待声音…）", "")
            self.overlay.closed.connect(self._on_overlay_closed)
        return self.overlay

    def _on_overlay_closed(self):
        # 悬浮窗被用户手动点击右上角关闭
        if self.overlay_chk.isChecked():
            self.overlay_chk.blockSignals(True)
            self.overlay_chk.setChecked(False)
            self.overlay_chk.blockSignals(False)

    def _on_overlay_chk_toggled(self, checked: bool):
        if checked:
            ol = self._ensure_overlay()
            ol.show()
        else:
            if self.overlay:
                self.overlay.hide()

    # ---- 控制 ----
    def on_start(self):
        dev = self.selected_input()
        if dev is None:
            self._log_gui("没有可选输入设备（请检查系统麦克风/扬声器权限）。")
            return
        src = self.src_combo.currentData()
        tgt = self.tgt_combo.currentData()
        model = self.model_combo.currentData()

        if self.overlay_chk.isChecked():
            ol = self._ensure_overlay()
            ol.show()

        try:
            from .live import LiveEngine
            self.engine = LiveEngine(
                input_device=dev["id"],
                source_iso=src, target_iso=tgt, asr_model=model,
                on_update=lambda state: self.subtitle_received.emit(state),
                on_log=lambda msg: self.log_received.emit(msg),
            )
            self.engine.start()
        except Exception as exc:
            self._log_gui(f"启动失败: {exc}")
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._log_gui(f"正在监听：{dev['label']} | {src} → {tgt} | {model}")
        self._start_level_timer()

    def on_stop(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._stop_level_timer()

    # ---- 回调（主线程槽） ----
    def _on_subtitle_gui(self, state: dict):
        if self.overlay and self.overlay.isVisible():
            # 上行译文，下行原文
            self.overlay.set_subtitle(state["src"], state["tgt"])
        self.level_label.setText(f"输入电平: —（已出字幕 {state['count']} 条）")

    def _start_level_timer(self):
        def update():
            if self.engine:
                lv = self.engine.capture.level
                txt = f"输入电平: {lv:.3f}"
                if lv > 0.02:
                    txt += "  🔊 有声"
                self.level_label.setText(txt)
        self._timer = QTimer()
        self._timer.timeout.connect(update)
        self._timer.start(400)

    def _stop_level_timer(self):
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.level_label.setText("输入电平: —")

    def _log_gui(self, msg: str):
        self.log_view.append(msg)

    def closeEvent(self, e):
        self.on_stop()
        if self.overlay:
            self.overlay.close()
        e.accept()


def run():
    app = QApplication(sys.argv)
    panel = LivePanel()
    panel.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
