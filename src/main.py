# -*- coding: utf-8 -*-
"""入口：`python -m app.main [url] --src en --tgt zh`。

不带参数则启动桌面 GUI；
带参数则以 CLI 方式处理（下载->转写->翻译->生成 SRT）。
"""

from __future__ import annotations

import argparse
import os
import sys


def cli(url: str, src: str, tgt: str, work: str, model: str, quality: str = "best"):
    from .pipeline import Pipeline

    pipe = Pipeline(work, asr_model=model)
    pipe.status_cb = lambda m: print("[状态]", m)
    result = pipe.run(url, src, tgt, quality=quality)
    srt = os.path.splitext(result["video"])[0] + ".srt"
    with open(srt, "w", encoding="utf-8") as f:
        for i, s in enumerate(result["segments"], 1):
            f.write(s.to_srt_block(i))
    print("完成，视频:", result["video"])
    print("字幕:", srt)
    print("共", len(result["segments"]), "条双字幕。")


def main():
    p = argparse.ArgumentParser(description="YouTube 本地双字幕")
    p.add_argument("url", nargs="?", help="视频链接 (YouTube / 抖音, 留空则启动 GUI)")
    p.add_argument("--src", default="en", help="源语言 ISO 代码 (默认 en)")
    p.add_argument("--tgt", default="zh", help="目标语言 ISO 代码 (默认 zh)")
    p.add_argument("--work", default=None, help="工作目录")
    p.add_argument("--model", default="small", help="whisper 模型大小")
    p.add_argument("--quality", "-q", default="best",
                   choices=["360p", "480p", "720p", "1080p", "1440p", "2160p", "best"],
                   help="下载画质 (默认 best 最高可用)")
    p.add_argument("--tui", action="store_true", help="启动终端交互界面 (TUI)")
    args = p.parse_args()

    work = args.work or os.path.join(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))), "outputs")

    if args.url:
        cli(args.url, args.src, args.tgt, work, args.model, args.quality)
    elif args.tui:
        from .tui import run_tui
        run_tui(work)
    else:
        try:
            from .player import run
            run(work, asr_model=args.model)
        except (ImportError, ModuleNotFoundError):
            from .tui import run_tui
            run_tui(work)


if __name__ == "__main__":
    main()
