# -*- coding: utf-8 -*-
"""桌面 GUI：播放 YouTube 视频并叠加“原文 + 译文”双字幕。"""

from __future__ import annotations

import os
import threading

from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtGui import QFont, QColor, QPainter
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QPushButton, QLabel, QTextEdit, QFrame,
    QSlider, QStyle, QMessageBox,
)

from .languages import code_list
from .pipeline import Pipeline


class SubtitleOverlay(QWidget):
    """半透明字幕覆盖层：两行（原文 + 译文）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._src = ""
        self._tgt = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_lines(self, src: str, tgt: str):
        self._src = src
        self._tgt = tgt
        self.update()

    def clear(self):
        self.set_lines("", "")

    def paintEvent(self, event):
        if not self._src and not self._tgt:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()

        from PySide6.QtCore import QRectF

        # 底部留白边距
        cur_bottom = self.height() - 24.0

        # 先画原文（靠下）
        if self._src:
            cur_bottom = self._draw_block(p, self._src, QColor(255, 255, 255, 245),
                                         QColor(0, 0, 0, 150), w, 13, cur_bottom) - 8.0

        # 再画译文（在原文上方，更显眼突出）
        if self._tgt:
            self._draw_block(p, self._tgt, QColor(255, 240, 120, 255),
                             QColor(0, 0, 0, 160), w, 16, cur_bottom)

    def _draw_block(self, p: QPainter, text: str, fg: QColor, bg: QColor,
                    total_w: float, font_size: int, bottom_y: float) -> float:
        font = QFont("Microsoft YaHei", font_size, QFont.Weight.DemiBold)
        p.setFont(font)
        fm = p.fontMetrics()

        max_text_w = max(200.0, total_w * 0.85)
        rect = fm.boundingRect(0, 0, int(max_text_w), 1000,
                               Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                               text)

        w = rect.width()
        h = rect.height()
        pad_x, pad_y = 12.0, 6.0

        x = (total_w - w) / 2.0
        top_y = bottom_y - h

        # 绘制圆角暗色背景条
        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(int(x - pad_x), int(top_y - pad_y),
                          int(w + pad_x * 2), int(h + pad_y * 2), 8, 8)

        # 绘制文本
        p.setPen(fg)
        p.drawText(int(x), int(top_y), int(w), int(h),
                   Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                   text)
        return top_y



class MainWindow(QMainWindow):
    pipeline_result = Signal(dict)
    pipeline_log = Signal(str)
    pipeline_error = Signal(str)

    def __init__(self, work_dir: str, asr_model: str = "small"):
        super().__init__()
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)
        self.segments = []
        self.current_video = None
        self._pipeline = None

        self.pipeline_result.connect(self._on_result)
        self.pipeline_log.connect(self._log)
        self.pipeline_error.connect(self._on_error)

        self.setWindowTitle("YouTube 本地双字幕")
        self.resize(1000, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # ---- 顶部控制条 ----
        bar = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("粘贴 YouTube 视频链接…")
        bar.addWidget(QLabel("链接:"))
        bar.addWidget(self.url_edit, 1)

        self.src_combo = QComboBox()
        self.tgt_combo = QComboBox()
        self.model_combo = QComboBox()
        for model in ["tiny", "base", "small", "medium", "large-v3"]:
            self.model_combo.addItem(f"whisper-{model}", model)
        self.model_combo.setCurrentIndex(2)  # 默认 small
        for code, name in code_list():
            self.src_combo.addItem(name, code)
            self.tgt_combo.addItem(name, code)
        # 默认 英文 -> 中文
        self.src_combo.setCurrentIndex(0)
        self.tgt_combo.setCurrentIndex(
            [self.tgt_combo.itemData(i) for i in range(self.tgt_combo.count())].index("zh"))
        bar.addWidget(QLabel("源语言:"))
        bar.addWidget(self.src_combo)
        bar.addWidget(QLabel("目标语言:"))
        bar.addWidget(self.tgt_combo)
        bar.addWidget(QLabel("模型:"))
        bar.addWidget(self.model_combo)
        bar.addWidget(QLabel("画质:"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItem("最高画质 (Best)", "best")
        self.quality_combo.addItem("1080p", "1080p")
        self.quality_combo.addItem("720p", "720p")
        self.quality_combo.addItem("480p", "480p")
        self.quality_combo.addItem("360p", "360p")
        self.quality_combo.setCurrentIndex(0)  # 默认最高画质
        bar.addWidget(self.quality_combo)

        self.fetch_btn = QPushButton("获取并生成双字幕")
        self.fetch_btn.clicked.connect(self.on_fetch)
        bar.addWidget(self.fetch_btn)
        root.addLayout(bar)

        # ---- 状态 / 进度 ----
        self.status = QLabel("就绪。首次会下载本地模型，之后完全离线。")
        root.addWidget(self.status)

        # ---- 视频区（带字幕覆盖层）----
        self.video_holder = QFrame()
        self.video_holder.setStyleSheet("background:#000;")
        holder_layout = QVBoxLayout(self.video_holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)

        self.video_widget = QVideoWidget()
        holder_layout.addWidget(self.video_widget)

        self.overlay = SubtitleOverlay(self.video_widget)
        self.overlay.setGeometry(0, 0, self.video_widget.width(),
                                 self.video_widget.height())

        root.addWidget(self.video_holder, 1)

        # ---- 播放控制 ----
        controls = QHBoxLayout()
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_MediaPlay))
        self.play_btn.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_btn)

        self.time_label = QLabel("00:00 / 00:00")
        controls.addWidget(self.time_label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.seek)
        controls.addWidget(self.slider, 1)
        root.addLayout(controls)

        # ---- 日志 ----
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(110)
        root.addWidget(QLabel("处理日志:"))
        root.addWidget(self.log_view)

        # ---- 媒体 ----
        self.player = QMediaPlayer(self)
        self.audio_out = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_out)
        self.player.setVideoOutput(self.video_widget)
        self.player.playbackStateChanged.connect(self._state_changed)
        self.player.positionChanged.connect(self._pos_changed)
        self.player.durationChanged.connect(self._dur_changed)

    # ---- 事件处理 ----
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_overlay()

    def _place_overlay(self):
        self.overlay.setGeometry(0, 0,
                                 self.video_widget.width(),
                                 self.video_widget.height())

    def on_fetch(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先输入 YouTube 链接。")
            return
        src = self.src_combo.currentData()
        tgt = self.tgt_combo.currentData()
        model = self.model_combo.currentData()
        quality = self.quality_combo.currentData()
        self.fetch_btn.setEnabled(False)
        self.log_view.clear()
        self.status.setText(f"使用 whisper-{model}，画质 {quality}，{src} → {tgt} …")
        self._pipeline = Pipeline(self.work_dir, asr_model=model)
        self._pipeline.status_cb = lambda m: self.pipeline_log.emit(m)

        def worker():
            try:
                result = self._pipeline.run(url, src, tgt, quality=quality)
                self.pipeline_result.emit(result)
            except Exception as exc:
                import traceback
                err_msg = f"出错: {exc}\n{traceback.format_exc()}"
                self.pipeline_error.emit(err_msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_error(self, err_msg: str):
        self.fetch_btn.setEnabled(True)
        self._log(err_msg)

    def _on_result(self, result):
        self.fetch_btn.setEnabled(True)
        self.segments = result["segments"]
        self.current_video = result["video"]
        self.player.setSource(QUrl.fromLocalFile(result["video"]))
        self.player.play()
        n = len(self.segments)
        self._log(f"成功：{result['title']}，{n} 条双字幕。点击播放即可观看。")
        # 导出 SRT
        import re
        base = re.sub(r'\.[^.]+$', '', self.current_video)
        srt = base + ".srt"
        with open(srt, "w", encoding="utf-8") as f:
            for i, s in enumerate(self.segments, 1):
                f.write(s.to_srt_block(i))
        self._log(f"已导出字幕: {srt}")

    # ---- 播放状态 ----
    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _state_changed(self, state):
        icon = (QStyle.StandardPixmap.SP_MediaPause
                if state == QMediaPlayer.PlaybackState.PlayingState
                else QStyle.StandardPixmap.SP_MediaPlay)
        self.play_btn.setIcon(self.style().standardIcon(icon))

    def seek(self, pos):
        self.player.setPosition(pos)

    def _pos_changed(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        self._update_subtitle(pos / 1000.0)
        self._update_time_label()

    def _dur_changed(self, dur):
        self.slider.setMaximum(int(dur))

    def _update_subtitle(self, t: float):
        src = tgt = ""
        for s in self.segments:
            if s.start <= t <= s.end:
                src, tgt = s.text, s.translated
                break
        self.overlay.set_lines(src, tgt)

    def _update_time_label(self):
        def f(ms):
            ms = max(0, int(ms))
            return f"{ms//60000:02d}:{(ms//1000)%60:02d}"
        d = self.player.duration()
        self.time_label.setText(
            f"{f(self.player.position())} / {f(d)}")

    def _log(self, msg):
        self.log_view.append(msg)
        self.status.setText(msg)


def run(work_dir: str, asr_model: str = "small"):
    import sys
    app = QApplication(sys.argv)
    win = MainWindow(work_dir, asr_model)
    win.show()
    sys.exit(app.exec())
