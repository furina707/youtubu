# -*- coding: utf-8 -*-
"""独立悬浮双字幕窗口：置顶、可拖动、半透明，显示“原文 + 译文”两行。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QApplication
)


class SubtitleOverlayWindow(QWidget):
    """无边框、置顶、可拖动的字幕悬浮窗。"""

    # 窗口关闭/隐藏时通知外部更新复选框
    closed = Signal()

    def __init__(self, src_label: str = "原文", tgt_label: str = "译文"):
        super().__init__()
        self.setWindowTitle("实时双字幕")
        # 置顶 + 无边框 + 工具窗（不进任务栏）
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._drag_pos: QPoint | None = None

        # 顶部小工具条
        top = QHBoxLayout()
        self.title = QLabel("实时双字幕")
        self.title.setStyleSheet("color:#9aa; font-size:9pt;")
        top.addWidget(self.title)
        top.addStretch(1)
        pin = QPushButton("📌")
        pin.setFixedSize(22, 22)
        pin.setToolTip("切换置顶")
        pin.setStyleSheet(self._btn_style())
        pin.clicked.connect(self._toggle_pin)
        top.addWidget(pin)
        close = QPushButton("✕")
        close.setFixedSize(22, 22)
        close.setToolTip("关闭字幕窗口")
        close.setStyleSheet(self._btn_style())
        close.clicked.connect(self.close)
        top.addWidget(close)

        # 两行字幕
        self.tgt_label = QLabel(tgt_label)
        self.tgt_label.setObjectName("tgt")
        self.tgt_label.setWordWrap(True)
        self.tgt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tgt_label.setStyleSheet(self._line_style(fg="#FFE066", big=True))

        self.src_label = QLabel(src_label)
        self.src_label.setObjectName("src")
        self.src_label.setWordWrap(True)
        self.src_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.src_label.setStyleSheet(self._line_style(fg="#FFFFFF", big=False))

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 6, 18, 12)
        root.setSpacing(2)
        root.addLayout(top)
        root.addWidget(self.tgt_label)
        root.addWidget(self.src_label)

        self.setStyleSheet("background: rgba(20,26,32,190); border-radius: 12px;")
        self.setMinimumSize(420, 90)
        self.resize(520, 120)
        # 初始放右下角
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 30,
                  screen.bottom() - self.height() - 50)
        self._pinned = True

    def _btn_style(self):
        return ("QPushButton{background:rgba(255,255,255,30);color:#fff;"
                "border:none;border-radius:6px;font-size:10pt;}"
                "QPushButton:hover{background:rgba(255,255,255,80);}")

    def _line_style(self, fg, big):
        size = "15pt" if big else "11pt"
        return (f"color:{fg}; font-size:{size}; font-weight:600;"
                "background:rgba(0,0,0,0);")

    def _toggle_pin(self):
        self._pinned = not self._pinned
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        if self._pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def set_subtitle(self, src: str, tgt: str):
        """更新两行字幕文本。"""
        self.src_label.setText(src or "")
        self.tgt_label.setText(tgt or "")
        self._resize_to_fit()

    def _resize_to_fit(self):
        # 让字适应内容
        self.adjustSize()
        w = max(420, min(self.sizeHint().width(), 900))
        self.resize(w, self.sizeHint().height())

    # 拖动
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    def closeEvent(self, e):
        super().closeEvent(e)
        self.closed.emit()
