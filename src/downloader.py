# -*- coding: utf-8 -*-
"""下载 YouTube / 抖音视频并抽取/标准化音轨（yt-dlp + ffmpeg）。"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from urllib.parse import urlparse

# 抖音要求的常规浏览器 UA（ttwid 注册接口与视频页共用）
_DOUYIN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_DOUYIN_HEADERS = {
    "Referer": "https://www.douyin.com/",
    "User-Agent": _DOUYIN_UA,
}


def ffmpeg_path() -> str:
    """返回可用的 ffmpeg 路径（imageio-ffmpeg 自带的即可）。"""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


class Downloader:
    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)
        self._ffmpeg = None

    @property
    def ffmpeg(self) -> str:
        if self._ffmpeg is None:
            self._ffmpeg = ffmpeg_path()
        return self._ffmpeg

    def sanitize(self, name: str) -> str:
        return re.sub(r'[\\/:*?"<>|]', '_', name).strip() or "video"

    # ------------------------------------------------------------------
    # 抖音 Cookie（ttwid）自动生成
    # ------------------------------------------------------------------
    def _douyin_cookiefile(self, force: bool = False) -> str | None:
        """生成/复用一份含 ttwid 的 Netscape cookie 文件。

        抖音公开视频也要求「新鲜 Cookie」，通过字节跳动 ttwid 注册接口
        免登录获取。缓存 7 天；force=True 用于失败后强制刷新。
        """
        path = os.path.join(self.work_dir, ".douyin_cookies.txt")
        if (not force and os.path.exists(path)
                and time.time() - os.path.getmtime(path) < 7 * 86400):
            return path

        payload = {
            "region": "cn",
            "aid": 1768,
            "needFid": False,
            "service": "www.ixigua.com",
            "migrate_info": {"ticket": "", "source": "node"},
            "cbUrlProtocol": "https",
            "union": True,
        }
        try:
            req = urllib.request.Request(
                "https://ttwid.bytedance.com/ttwid/union/register/",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": _DOUYIN_UA,
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                set_cookie = resp.headers.get("Set-Cookie", "") or ""
                try:
                    body = json.loads(resp.read().decode("utf-8", "ignore"))
                except Exception:
                    body = {}
            ttwid = None
            m = re.search(r"ttwid=([^;]+)", set_cookie)
            if m:
                ttwid = m.group(1)
            else:
                # 部分响应把 ttwid 放在 JSON body 的 data.ttwid
                ttwid = (body.get("data") or {}).get("ttwid")
            if not ttwid:
                return None
            with open(path, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write(f".douyin.com\tTRUE\t/\tTRUE\t0\tttwid\t{ttwid}\n")
            return path
        except Exception:
            return None

    def _extract(self, opts: dict, url: str, download: bool) -> dict:
        """yt-dlp 提取封装：ttwid 过期报 Fresh cookies 时自动刷新重试一次。"""
        import yt_dlp
        from yt_dlp.utils import DownloadError
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=download)
                return ydl.sanitize_info(info)
        except DownloadError as exc:
            cf = opts.get("cookiefile")
            if cf and "Fresh cookies" in str(exc):
                fresh = self._douyin_cookiefile(force=True)
                if fresh:
                    opts = dict(opts, cookiefile=fresh)
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(url, download=download)
                        return ydl.sanitize_info(info)
            raise

    @staticmethod
    def detect_platform(url: str) -> str:
        """识别链接所属平台：douyin / youtube / generic。"""
        try:
            host = (urlparse(url).netloc or "").lower()
        except Exception:
            host = ""
        if any(h in host for h in ("douyin.com", "iesdouyin.com")):
            return "douyin"
        if any(h in host for h in ("youtube.com", "youtu.be", "youtube-nocookie.com")):
            return "youtube"
        return "generic"

    @staticmethod
    def build_format_selector(quality: str = "best", platform: str = "youtube") -> str:
        """根据画质要求与平台构造 yt-dlp format 字符串。

        抖音多为单文件渐进式流（音视频合一），避免依赖 ext=mp4/m4a
        的分轨匹配，优先选整条流，失败再回退 best。
        """
        q = str(quality).lower().strip()
        if platform == "douyin":
            if q in ("best", "max", "highest", "最高", "最高画质"):
                return "bestvideo+bestaudio/best"
            digits = "".join(filter(str.isdigit, q))
            height = int(digits) if digits else 720
            return (
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/"
                "best"
            )
        if q in ("best", "max", "highest", "最高", "最高画质"):
            return (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo+bestaudio/"
                "best[ext=mp4]/best"
            )
        # 提取数字高度，如 "1080p" -> 1080
        digits = "".join(filter(str.isdigit, q))
        height = int(digits) if digits else 720
        return (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={height}][ext=mp4]/"
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/"
            "best"
        )

    def download(self, url: str, out_dir: str | None = None,
                 progress=None, quality: str = "best",
                 cookies_from_browser: str | None = None) -> dict:
        """下载 YouTube / 抖音视频为 mp4，返回 {title, video: 路径, audio: 路径}。

        cookies_from_browser: 可选浏览器名 (chrome/edge/firefox/brave/safari/opera/vivaldi)，
        用于借助浏览器登录态下载需要登录的抖音视频。
        """
        import yt_dlp

        out_dir = out_dir or self.work_dir
        os.makedirs(out_dir, exist_ok=True)
        self._ffmpeg = self.ffmpeg  # 确保 imageio-ffmpeg 已就绪

        # imageio-ffmpeg 的二进制名是 ffmpeg-win-*.exe（不是 ffmpeg.exe），
        # 因此 ffmpeg_location 必须指向该二进制本身的完整路径，yt-dlp 才能识别。
        ffmpeg_bin = self._ffmpeg

        def hook(d):
            if progress is not None:
                progress(d)

        platform = self.detect_platform(url)
        fmt = self.build_format_selector(quality, platform)
        opts = {
            "format": fmt,
            "merge_output_format": "mp4",
            "outtmpl": os.path.join(out_dir, "%(title).80s.%(ext)s"),
            "ffmpeg_location": ffmpeg_bin,
            "restrictfilenames": False,
            "noplaylist": True,
            "retries": 5,
            "fragment_retries": 5,
            "progress_hooks": [hook],
            "quiet": False,
            "no_warnings": True,
        }
        if platform == "douyin":
            # 抖音接口对请求头敏感，带上站点 Referer 与常规 UA 提升成功率
            opts["http_headers"] = dict(_DOUYIN_HEADERS)
            # 公开视频也需要「新鲜 Cookie」：自动生成 ttwid（不依赖浏览器）
            if not cookies_from_browser:
                cf = self._douyin_cookiefile()
                if cf:
                    opts["cookiefile"] = cf
        if cookies_from_browser:
            opts["cookiesfrombrowser"] = (cookies_from_browser,)
        info = self._extract(opts, url, download=True)

        title = info.get("title", "video")
        safe = self.sanitize(title)
        # 解析实际下载文件的路径（合并/后处理后的最终 mp4）
        video = None
        rd = info.get("requested_downloads")
        if rd:
            video = rd[0].get("filepath")
        if not video or not os.path.exists(str(video)):
            video = os.path.join(out_dir, safe + ".mp4")
        video = str(video)
        audio = os.path.join(out_dir, safe + ".wav")
        self.extract_audio(video, audio)
        return {"title": title, "video": video, "audio": audio}

    def extract_audio(self, video: str, audio: str, sample_rate: int = 16000):
        """抽取音轨为 16k 单声道 WAV，供 whisper 使用。"""
        import subprocess
        ffmpeg = self.ffmpeg  # 解析 ffmpeg 路径（首次自动就绪）
        cmd = [
            ffmpeg, "-y", "-i", video,
            "-vn", "-ac", "1", "-ar", str(sample_rate),
            "-c:a", "pcm_s16le", audio,
        ]
        subprocess.run(cmd, check=True, capture_output=False)

    def inspect_info(self, url: str, cookies_from_browser: str | None = None) -> dict:
        """解析视频基本信息与可用清晰度列表（不下载）。"""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        if self.detect_platform(url) == "douyin":
            opts["http_headers"] = dict(_DOUYIN_HEADERS)
            if not cookies_from_browser:
                cf = self._douyin_cookiefile()
                if cf:
                    opts["cookiefile"] = cf
        if cookies_from_browser:
            opts["cookiesfrombrowser"] = (cookies_from_browser,)
        info = self._extract(opts, url, download=False)

        formats = info.get("formats", [])
        heights = set()
        for f in formats:
            h = f.get("height")
            if h and f.get("vcodec") != "none":
                heights.add(int(h))
        sorted_heights = sorted(list(heights), reverse=True)
        return {
            "platform": self.detect_platform(url),
            "title": info.get("title", ""),
            "uploader": info.get("uploader", ""),
            "duration": info.get("duration", 0),
            "resolutions": sorted_heights,
            "description": info.get("description", "")[:120] if info.get("description") else "",
        }
