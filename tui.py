# -*- coding: utf-8 -*-
"""根目录快捷启动脚本：启动 YouTube 本地双字幕与下载 TUI 交互界面。"""

import os
import sys

# 确保项目根目录在 sys.path 中
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.tui import run_tui

if __name__ == "__main__":
    run_tui()
