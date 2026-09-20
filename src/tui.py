# -*- coding: utf-8 -*-
"""YouTube 本地双字幕与视频下载终端交互界面 (TUI)。

支持键盘上下键/数字快捷键导航、画质选择、实时下载进度条、
Whisper 本地模型选择、离线双语翻译以及输出文件管理。
"""

from __future__ import annotations

import os
import sys
import time
import shutil
import subprocess

try:
    import colorama
    from colorama import Fore, Back, Style
    colorama.init(autoreset=True)
except ImportError:
    class _EmptyStyle:
        def __getattr__(self, name):
            return ""
    Fore = Back = Style = _EmptyStyle()

from .languages import LANG_MAP, code_list
from .downloader import Downloader
from .pipeline import Pipeline


def clear_screen():
    """跨平台清屏。"""
    os.system("cls" if os.name == "nt" else "clear")


def format_size(size_bytes: int | float) -> str:
    """人性化显示文件字节大小。"""
    if not size_bytes or size_bytes <= 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def format_duration(seconds: int | float) -> str:
    """人性化显示时长。"""
    if not seconds or seconds <= 0:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def get_clipboard_text() -> str | None:
    """获取剪贴板中的链接（若以 http 开头）。"""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        if text and text.strip().startswith(("http://", "https://")):
            return text.strip()
    except Exception:
        pass
    return None


def draw_header(subtitle: str = ""):
    """打印漂亮的终端横幅。"""
    cols = shutil.get_terminal_size((80, 24)).columns
    width = min(cols - 2, 72)
    border = "═" * (width - 2)
    title = "本地双语字幕 & 视频下载器 (YouTube / 抖音)"
    
    print(Fore.CYAN + f"╔{border}╗")
    print(Fore.CYAN + f"║" + Fore.WHITE + Style.BRIGHT + title.center(width - 2) + Fore.CYAN + "║")
    if subtitle:
        sub_str = f"「 {subtitle} 」"
        print(Fore.CYAN + f"║" + Fore.YELLOW + sub_str.center(width - 2) + Fore.CYAN + "║")
    print(Fore.CYAN + f"╚{border}╝" + Style.RESET_ALL)
    print()


def interactive_select(title: str, options: list[str], default_idx: int = 0) -> int:
    """支持键盘方向键/数字快捷键的交互式单选菜单。"""
    is_windows = os.name == "nt"
    has_msvcrt = False
    if is_windows and sys.stdin.isatty():
        try:
            import msvcrt
            has_msvcrt = True
        except ImportError:
            has_msvcrt = False

    current_idx = max(0, min(default_idx, len(options) - 1))

    if not has_msvcrt:
        # 回退至兼容模式输入
        print(Fore.YELLOW + f"{title}:" + Style.RESET_ALL)
        for i, opt in enumerate(options, 1):
            def_mark = " (默认)" if (i - 1) == default_idx else ""
            print(f"  [{i}] {opt}{def_mark}")
        while True:
            choice = input(Fore.GREEN + f"请输入序号 (1-{len(options)}, 留空默认[{default_idx+1}]): " + Style.RESET_ALL).strip()
            if not choice:
                return default_idx
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                return int(choice) - 1
            print(Fore.RED + "无效序号，请重新输入！" + Style.RESET_ALL)

    import msvcrt
    # 动态就地重绘菜单
    num_lines = len(options) + 2
    first_render = True

    while True:
        if not first_render:
            # 向上移动光标覆盖重绘
            sys.stdout.write(f"\033[{num_lines}A")
        first_render = False

        print(Fore.YELLOW + Style.BRIGHT + f"▶ {title} （↑/↓ 切换，回车确认，数字直选）" + Style.RESET_ALL)
        for i, opt in enumerate(options):
            if i == current_idx:
                print(Fore.BLACK + Back.CYAN + f"  👉 [{i+1}] {opt} " + Style.RESET_ALL)
            else:
                print(Fore.WHITE + f"     [{i+1}] {opt}" + Style.RESET_ALL)
        print(Fore.LIGHTBLACK_EX + "  " + "─" * 40 + Style.RESET_ALL)
        sys.stdout.flush()

        ch = msvcrt.getch()
        if ch in (b'\x00', b'\xe0'):
            # 扩展键（方向键）
            key = msvcrt.getch()
            if key == b'H':  # Up
                current_idx = (current_idx - 1) % len(options)
            elif key == b'P':  # Down
                current_idx = (current_idx + 1) % len(options)
        elif ch in (b'\r', b'\n'):
            break
        elif ch in (b'\x1b', b'q', b'Q'):  # Esc 或 q 返回默认
            break
        elif ch.isdigit():
            val = int(ch.decode("latin1", "ignore"))
            if 1 <= val <= len(options):
                current_idx = val - 1
                break

    return current_idx


def prompt_url(default_url: str = "") -> str:
    """输入或粘贴视频链接（YouTube / 抖音），支持自动检测剪贴板。"""
    clip = get_clipboard_text()
    hint_url = default_url or clip or ""

    print(Fore.YELLOW + "请输入视频链接 (YouTube / 抖音):" + Style.RESET_ALL)
    if hint_url:
        platform = Downloader.detect_platform(hint_url)
        plat_str = {"douyin": "抖音", "youtube": "YouTube"}.get(platform, "未知平台")
        print(Fore.LIGHTBLACK_EX +
              f"检测到链接 [{plat_str}] (回车直接使用): {hint_url}" +
              Style.RESET_ALL)

    while True:
        raw = input(Fore.GREEN + "URL > " + Style.RESET_ALL).strip()
        if not raw:
            if hint_url:
                return hint_url
            print(Fore.RED + "链接不能为空，请重新输入！" + Style.RESET_ALL)
            continue
        return raw


def show_video_preview(dl: Downloader, url: str) -> dict | None:
    """下载前解析并展示视频信息（标题 / 可用画质），返回 info 或 None。"""
    print()
    print(Fore.CYAN + "正在解析视频信息..." + Style.RESET_ALL)
    info = None
    try:
        info = dl.inspect_info(url)
    except Exception as exc:
        print(Fore.YELLOW +
              f"⚠ 视频信息预解析失败（不影响下载尝试）: {exc}" +
              Style.RESET_ALL)
        if any(k in str(exc).lower() for k in ("login", "cookie", "登录", "verify")):
            print(Fore.YELLOW +
                  "  提示: 该视频可能需要登录态，可稍后在浏览器登录抖音后重试。" +
                  Style.RESET_ALL)
        return None

    plat_name = {"douyin": "抖音", "youtube": "YouTube"}.get(
        info.get("platform", ""), "未知")
    print()
    print(Fore.GREEN + Style.BRIGHT + "--------- 视频信息预览 ---------" + Style.RESET_ALL)
    print(Fore.WHITE + "平台: " + Fore.LIGHTCYAN_EX + plat_name)
    print(Fore.WHITE + "标题: " + Fore.YELLOW + info.get("title", "未知"))
    print(Fore.WHITE + "作者: " + Fore.CYAN + info.get("uploader", "未知"))
    print(Fore.WHITE + "时长: " + Fore.GREEN + format_duration(info.get("duration", 0)))
    res_list = info.get("resolutions", [])
    if res_list:
        best = res_list[0]
        res_str = ", ".join(f"{h}p" for h in res_list[:6])
        print(Fore.WHITE + "可用画质: " + Fore.LIGHTBLACK_EX + res_str)
        print(Fore.WHITE + "本次下载: " + Fore.GREEN + Style.BRIGHT +
              f"{best}p （最高可用画质）" + Style.RESET_ALL)
    else:
        print(Fore.WHITE + "本次下载: " + Fore.GREEN + Style.BRIGHT +
              "最高可用画质" + Style.RESET_ALL)
    print(Fore.GREEN + Style.BRIGHT + "--------------------------------" + Style.RESET_ALL)
    return info


def select_asr_model() -> str:
    """选择 Whisper ASR 模型。"""
    models = [
        "whisper-small （推荐，中英日韩综合准确度高，显存需求低）",
        "whisper-base （较快，资源消耗少）",
        "whisper-tiny （最快，适合实时预览或低配机器）",
        "whisper-medium （更精准，模型约 1.5GB）",
        "whisper-large-v3 （最高精准度，需 6GB+ 显存）",
    ]
    raw_vals = ["small", "base", "tiny", "medium", "large-v3"]
    idx = interactive_select("选择语音识别 (Whisper) 模型大小", models, default_idx=0)
    return raw_vals[idx]


def select_language(label: str, default_code: str = "en") -> str:
    """选择源语言或目标语言。"""
    all_langs = code_list()
    names = [f"{name} ({code})" for code, name in all_langs]
    codes = [code for code, name in all_langs]
    default_idx = 0
    if default_code in codes:
        default_idx = codes.index(default_code)
    idx = interactive_select(f"选择{label}", names, default_idx=default_idx)
    return codes[idx]


def render_progress(d):
    """绘制美观的动态下载进度条。"""
    status = d.get("status")
    if status == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        downloaded = d.get("downloaded_bytes", 0)
        speed = d.get("speed") or 0
        eta = d.get("eta") or 0

        percent = (downloaded / total * 100.0) if total > 0 else 0.0
        bar_len = 28
        filled = int(bar_len * percent / 100.0) if total > 0 else 0
        bar = "█" * filled + "░" * (bar_len - filled)

        speed_str = f"{speed/1024/1024:.2f} MB/s" if speed else "— MB/s"
        dl_str = f"{format_size(downloaded)}/{format_size(total)}" if total else format_size(downloaded)
        eta_str = f"ETA {format_duration(eta)}" if eta else ""

        sys.stdout.write(
            f"\r{Fore.CYAN}[{bar}] {Fore.YELLOW}{percent:5.1f}% "
            f"{Fore.WHITE}{dl_str} {Fore.GREEN}{speed_str} {Fore.LIGHTBLACK_EX}{eta_str}{Style.RESET_ALL}   "
        )
        sys.stdout.flush()
    elif status == "finished":
        sys.stdout.write(f"\n{Fore.GREEN}✔ 视频流下载完成，正在合并音频与后处理...\n{Style.RESET_ALL}")
        sys.stdout.flush()


def action_download_video(work_dir: str):
    """[功能 1] 仅下载视频 (YouTube / 抖音)，固定最高画质。"""
    clear_screen()
    draw_header("下载视频 (YouTube / 抖音)")
    url = prompt_url()

    dl = Downloader(work_dir)
    show_video_preview(dl, url)

    print()
    print(Fore.CYAN + "开始下载最高画质..." + Style.RESET_ALL)
    try:
        res = dl.download(url, quality="best", progress=render_progress)
        print()
        print(Fore.GREEN + Style.BRIGHT + "================ 下载成功 ================" + Style.RESET_ALL)
        print(Fore.WHITE + "视频标题: " + Fore.YELLOW + res.get("title", ""))
        print(Fore.WHITE + "视频文件: " + Fore.CYAN + res.get("video", ""))
        if os.path.exists(res.get("video", "")):
            print(Fore.WHITE + "视频大小: " + Fore.GREEN + format_size(os.path.getsize(res["video"])))
        print(Fore.WHITE + "提取音频: " + Fore.CYAN + res.get("audio", ""))
        if os.path.exists(res.get("audio", "")):
            print(Fore.WHITE + "音频大小: " + Fore.GREEN + format_size(os.path.getsize(res["audio"])))
        print(Fore.GREEN + Style.BRIGHT + "==========================================" + Style.RESET_ALL)
    except Exception as exc:
        print()
        print(Fore.RED + f"下载失败: {exc}" + Style.RESET_ALL)

    input(Fore.LIGHTBLACK_EX + "\n按回车键返回主菜单..." + Style.RESET_ALL)


def action_pipeline(work_dir: str):
    """[功能 2] 下载 + 本地语音转写 + 离线翻译 + 导出字幕，固定最高画质。"""
    clear_screen()
    draw_header("一键生成双语字幕 (Pipeline)")
    url = prompt_url()

    dl = Downloader(work_dir)
    show_video_preview(dl, url)

    model = select_asr_model()
    src = select_language("源语言（视频原音语言）", default_code="en")
    tgt = select_language("目标语言（翻译输出语言）", default_code="zh")

    clear_screen()
    draw_header("正在执行双语字幕流水线")
    print(Fore.WHITE + "链接: " + Fore.CYAN + url)
    print(Fore.WHITE + "画质: " + Fore.YELLOW + "最高可用" + Fore.WHITE + " | Whisper 模型: " + Fore.YELLOW + f"whisper-{model}")
    print(Fore.WHITE + "语言: " + Fore.GREEN + f"{src} → {tgt}")
    print(Fore.LIGHTBLACK_EX + "─" * 60 + Style.RESET_ALL)

    pipe = Pipeline(work_dir, asr_model=model)
    pipe.status_cb = lambda msg: print(Fore.CYAN + f"[{time.strftime('%H:%M:%S')}] " + Fore.WHITE + msg + Style.RESET_ALL)

    try:
        result = pipe.run(url, src, tgt, quality="best")
        # 写入 SRT
        base_name = os.path.splitext(result["video"])[0]
        srt_file = base_name + ".srt"
        with open(srt_file, "w", encoding="utf-8") as f:
            for i, s in enumerate(result["segments"], 1):
                f.write(s.to_srt_block(i))

        print()
        print(Fore.GREEN + Style.BRIGHT + "================ 处理完成 ================" + Style.RESET_ALL)
        print(Fore.WHITE + "视频标题: " + Fore.YELLOW + result["title"])
        print(Fore.WHITE + "视频文件: " + Fore.CYAN + result["video"])
        print(Fore.WHITE + "字幕文件: " + Fore.GREEN + srt_file)
        print(Fore.WHITE + "字幕条数: " + Fore.CYAN + str(len(result["segments"])))
        print(Fore.GREEN + Style.BRIGHT + "==========================================" + Style.RESET_ALL)

        # 打印部分字幕示例
        if result["segments"]:
            print(Fore.YELLOW + "\n字幕片段预览 (前 3 句):" + Style.RESET_ALL)
            for seg in result["segments"][:3]:
                print(f"  ⏱ {format_duration(seg.start)} -> {format_duration(seg.end)}")
                print(Fore.LIGHTWHITE_EX + f"    原: {seg.text}" + Style.RESET_ALL)
                print(Fore.LIGHTCYAN_EX + f"    译: {getattr(seg, 'translated', '')}" + Style.RESET_ALL)

    except Exception as exc:
        print()
        print(Fore.RED + f"流水线处理失败: {exc}" + Style.RESET_ALL)

    input(Fore.LIGHTBLACK_EX + "\n按回车键返回主菜单..." + Style.RESET_ALL)


def action_inspect_video(work_dir: str):
    """[功能 3] 查询视频详细信息与画质列表。"""
    clear_screen()
    draw_header("查询视频格式与清晰度")
    url = prompt_url()

    print()
    print(Fore.CYAN + "正在获取视频信息（无需下载）..." + Style.RESET_ALL)
    dl = Downloader(work_dir)
    try:
        info = dl.inspect_info(url)
        plat_name = {"douyin": "抖音", "youtube": "YouTube"}.get(
            info.get("platform", ""), "未知")
        print()
        print(Fore.GREEN + Style.BRIGHT + "---------------- 视频详情 ----------------" + Style.RESET_ALL)
        print(Fore.WHITE + "平台: " + Fore.LIGHTCYAN_EX + plat_name)
        print(Fore.WHITE + "标题: " + Fore.YELLOW + info.get("title", "未知"))
        print(Fore.WHITE + "作者: " + Fore.CYAN + info.get("uploader", "未知"))
        print(Fore.WHITE + "时长: " + Fore.GREEN + format_duration(info.get("duration", 0)))
        res_list = info.get("resolutions", [])
        if res_list:
            res_str = ", ".join([f"{h}p" for h in res_list])
            print(Fore.WHITE + "可用画质: " + Fore.LIGHTGREEN_EX + res_str)
        else:
            print(Fore.WHITE + "可用画质: " + Fore.LIGHTBLACK_EX + "未知")
        if info.get("description"):
            print(Fore.WHITE + "简介: " + Fore.LIGHTBLACK_EX + info["description"].replace("\n", " ")[:90] + "...")
        print(Fore.GREEN + Style.BRIGHT + "------------------------------------------" + Style.RESET_ALL)
    except Exception as exc:
        print(Fore.RED + f"获取视频信息失败: {exc}" + Style.RESET_ALL)

    input(Fore.LIGHTBLACK_EX + "\n按回车键返回主菜单..." + Style.RESET_ALL)


def action_view_outputs(work_dir: str):
    """[功能 4] 浏览已下载文件并支持打开文件夹。"""
    clear_screen()
    draw_header("已下载文件列表")
    print(Fore.WHITE + "保存目录: " + Fore.CYAN + work_dir + Style.RESET_ALL)
    print()

    if not os.path.exists(work_dir):
        print(Fore.YELLOW + "当前输出目录为空。" + Style.RESET_ALL)
    else:
        files = os.listdir(work_dir)
        valid_files = [f for f in files if f.endswith((".mp4", ".wav", ".srt", ".m4a"))]
        if not valid_files:
            print(Fore.YELLOW + "当前输出目录暂无视频或字幕文件。" + Style.RESET_ALL)
        else:
            print(Fore.LIGHTBLACK_EX + f"{'文件名':<46} {'大小':<10} {'最后修改':<18}" + Style.RESET_ALL)
            print(Fore.LIGHTBLACK_EX + "─" * 76 + Style.RESET_ALL)
            for f in sorted(valid_files):
                full = os.path.join(work_dir, f)
                sz = format_size(os.path.getsize(full)) if os.path.isfile(full) else "—"
                mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(full)))
                color = Fore.CYAN if f.endswith(".mp4") else (Fore.GREEN if f.endswith(".srt") else Fore.WHITE)
                disp_name = (f[:42] + "...") if len(f) > 45 else f
                print(f"{color}{disp_name:<46}{Fore.YELLOW}{sz:<10}{Fore.LIGHTBLACK_EX}{mtime:<18}{Style.RESET_ALL}")

    print()
    opts = [
        "返回主菜单",
        "在 Windows 资源管理器中打开该文件夹",
    ]
    sel = interactive_select("操作", opts, default_idx=0)
    if sel == 1:
        try:
            if os.name == "nt":
                os.startfile(work_dir)
            else:
                subprocess.Popen(["xdg-open", work_dir])
            print(Fore.GREEN + "已在文件资源管理器中打开。" + Style.RESET_ALL)
            time.sleep(1)
        except Exception as exc:
            print(Fore.RED + f"打开失败: {exc}" + Style.RESET_ALL)


def action_launch_live():
    """[功能 5] 启动实时字幕面板 (Tkinter 标准库版)。"""
    clear_screen()
    draw_header("启动实时双字幕面板")
    print(Fore.CYAN + "正在唤起基于 Python 标准库 Tkinter 的桌面控制面板与置顶悬浮窗..." + Style.RESET_ALL)
    try:
        from .ui_tk_main import run as run_tk
        run_tk()
    except Exception as exc:
        print(Fore.RED + f"启动实时面板失败: {exc}" + Style.RESET_ALL)
        input(Fore.LIGHTBLACK_EX + "\n按回车键返回主菜单..." + Style.RESET_ALL)


def run_tui(work_dir: str | None = None):
    """TUI 主循环。"""
    work = work_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs"
    )
    os.makedirs(work, exist_ok=True)

    menu_options = [
        "📥 下载视频 （YouTube / 抖音，自选画质 360p ~ 4K / Best）",
        "🎬 一键生成双语字幕 （下载 + Whisper 转写 + NLLB 离线翻译 + 导出 SRT）",
        "🔍 查询视频信息与格式 （检测标题、时长、支持的清晰度）",
        "📁 查看已生成文件 （浏览输出目录 outputs / 打开文件夹）",
        "🎙️ 启动实时双字幕 （捕获扬声器声音，悬浮置顶字幕窗口）",
        "🚪 退出",
    ]

    while True:
        clear_screen()
        draw_header("终端交互主菜单 (TUI)")
        print(Fore.WHITE + "工作目录: " + Fore.CYAN + work + Style.RESET_ALL)
        print()

        choice = interactive_select("请选择操作功能", menu_options, default_idx=0)

        if choice == 0:
            action_download_video(work)
        elif choice == 1:
            action_pipeline(work)
        elif choice == 2:
            action_inspect_video(work)
        elif choice == 3:
            action_view_outputs(work)
        elif choice == 4:
            action_launch_live()
        elif choice == 5:
            clear_screen()
            print(Fore.GREEN + "感谢使用，再见！" + Style.RESET_ALL)
            break


if __name__ == "__main__":
    run_tui()
