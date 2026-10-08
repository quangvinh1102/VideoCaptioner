"""Video download worker thread (yt-dlp)."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional

import requests
import yt_dlp
from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.utils.download_helper import (
    BROWSER_CANDIDATES,
    apply_auth_opts,
    apply_ffmpeg_opts,
    default_cookie_path,
    friendly_download_error,
    is_bilibili_url,
)
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("video_download_thread")


class VideoDownloadThread(QThread):
    """视频下载线程类"""

    finished = pyqtSignal(str)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, url: str, work_dir: str, cookiefile: Optional[str] = None):
        super().__init__()
        self.url = url
        self.work_dir = work_dir
        self.cookiefile = cookiefile

    def run(self):
        try:
            video_file_path, *_rest = self.download()
            if not video_file_path:
                raise RuntimeError("Tải xong nhưng không tìm thấy file video")
            self.finished.emit(video_file_path)
        except Exception as e:
            logger.exception("下载视频失败: %s", str(e))
            self.error.emit(friendly_download_error(e, self.url))

    def progress_hook(self, d):
        """下载进度回调函数"""
        if d.get("status") != "downloading":
            return
        try:
            percent = str(d.get("_percent_str") or "0").strip()
            speed = str(d.get("_speed_str") or "?").strip()
            for code in ("\x1b[0;94m", "\x1b[0;32m", "\x1b[0m"):
                percent = percent.replace(code, "")
                speed = speed.replace(code, "")
            percent = percent.replace("%", "").strip() or "0"
            pct = int(float(percent))
            self.progress.emit(pct, f"Đang tải: {pct}%  tốc độ: {speed}")
        except Exception:
            pass

    def sanitize_filename(self, name: str, replacement: str = "_") -> str:
        forbidden_chars = r'<>:"/\\|?*'
        sanitized = re.sub(f"[{re.escape(forbidden_chars)}]", replacement, name)
        sanitized = re.sub(r"[\0-\31]", "", sanitized).rstrip(" .")
        max_length = 255
        if len(sanitized) > max_length:
            base, ext = os.path.splitext(sanitized)
            sanitized = base[: max_length - len(ext)] + ext
        windows_reserved = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
        if os.path.splitext(sanitized)[0].upper() in windows_reserved:
            sanitized = f"{sanitized}_"
        return sanitized or "default_filename"

    def download(self, need_subtitle: bool = True, need_thumbnail: bool = False):
        """下载视频 — retry on incomplete CDN transfers."""
        logger.info("开始下载视频: %s", self.url)

        format_candidates = [
            # Prefer H.264 — AV1 + filter burn often breaks with CUDA / is slow to decode
            (
                "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo[vcodec*=h264][ext=mp4]+bestaudio[ext=m4a]/"
                "best[vcodec^=avc1][ext=mp4]/best[ext=mp4]/best"
            ),
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "best[ext=mp4]/best",
            "best",
        ]

        last_error: Optional[BaseException] = None

        for attempt_opts in self._auth_attempts():
            cookie = attempt_opts.get("cookiefile")
            browser = attempt_opts.get("cookiesfrombrowser")
            if cookie:
                self.progress.emit(1, "Dùng cookies file...")
            elif browser:
                self.progress.emit(1, f"Thử cookies từ {browser[0]}...")

            auth_failed = False
            for fmt_index, fmt in enumerate(format_candidates):
                for network_try in range(1, 5):
                    opts = self._build_ydl_opts(fmt, need_subtitle, need_thumbnail)
                    opts.update(attempt_opts)
                    try:
                        if network_try > 1 or fmt_index > 0:
                            self.progress.emit(
                                5,
                                f"Tiếp tục tải dở (lần {network_try}/4, format {fmt_index + 1})...",
                            )
                            time.sleep(1.5)
                        return self._download_once(opts)
                    except Exception as exc:
                        last_error = exc
                        msg = str(exc).lower()
                        logger.warning(
                            "Download failed (fmt=%s try=%s): %s",
                            fmt,
                            network_try,
                            exc,
                        )
                        if self._is_auth_error(msg):
                            auth_failed = True
                            break
                        if self._is_incomplete_error(msg):
                            continue
                        break  # try next format
                if auth_failed:
                    break
            if not auth_failed:
                break

        assert last_error is not None
        raise last_error

    @staticmethod
    def _is_auth_error(msg: str) -> bool:
        return any(
            x in msg
            for x in (
                "412",
                "403",
                "precondition",
                "forbidden",
                "cookie",
                "dpapi",
                "could not copy",
                "failed to decrypt",
            )
        )

    @staticmethod
    def _is_incomplete_error(msg: str) -> bool:
        return any(
            x in msg
            for x in (
                "more expected",
                "bytes read",
                "incomplete",
                "timed out",
                "timeout",
                "connection reset",
                "10054",
                "eof occurred",
                "fragment",
                "unable to download",
                "got error",
            )
        )

    def _build_ydl_opts(
        self, fmt: str, need_subtitle: bool, need_thumbnail: bool
    ) -> dict:
        opts = {
            "outtmpl": {
                "default": "%(title).200s.%(ext)s",
                "subtitle": "【下载字幕】.%(ext)s",
                "thumbnail": "thumbnail",
            },
            "format": fmt,
            "progress_hooks": [self.progress_hook],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "writeautomaticsub": need_subtitle,
            "writethumbnail": need_thumbnail,
            "thumbnail_format": "jpg",
            "noplaylist": True,
            "continuedl": True,
            "retries": 25,
            "fragment_retries": 25,
            "file_access_retries": 15,
            "extractor_retries": 5,
            "socket_timeout": 60,
            "concurrent_fragment_downloads": 1,
            "http_chunk_size": 5_242_880,  # 5MB — smaller chunks resume better
        }
        opts = apply_ffmpeg_opts(opts)
        if opts.get("ffmpeg_location"):
            opts["format"] = fmt
        return opts

    def _auth_attempts(self) -> list[dict]:
        from videocaptioner.core.utils.download_helper import (
            browser_cookies_supported,
            resolve_cookie_file,
        )

        attempts: list[dict] = []
        cookie = resolve_cookie_file(self.cookiefile)
        if cookie is not None:
            attempts.append(apply_auth_opts({}, self.url, cookiefile=str(cookie)))
            return attempts

        if is_bilibili_url(self.url):
            # Packaged exe: DPAPI browser cookies fail — try headers-only first
            if browser_cookies_supported():
                for browser in BROWSER_CANDIDATES:
                    opts = apply_auth_opts(
                        {}, self.url, allow_browser_cookies=False
                    )
                    opts["cookiesfrombrowser"] = (browser,)
                    attempts.append(opts)
            fallback = apply_auth_opts({}, self.url, allow_browser_cookies=False)
            attempts.append(fallback)
        else:
            attempts.append(apply_auth_opts({}, self.url, allow_browser_cookies=False))
        return attempts

    def _download_once(self, initial_ydl_opts: dict):
        with yt_dlp.YoutubeDL(initial_ydl_opts) as ydl:
            info_dict = ydl.extract_info(self.url, download=False)
            video_title = self.sanitize_filename(info_dict.get("title", "MyVideo"))
            video_work_dir = Path(self.work_dir) / self.sanitize_filename(video_title)
            video_work_dir.mkdir(parents=True, exist_ok=True)

            subtitle_language = info_dict.get("language")
            if subtitle_language:
                subtitle_language = subtitle_language.lower().split("-")[0]

            subtitle_download_link = None
            try:
                automatic_captions = info_dict.get("automatic_captions") or {}
                if automatic_captions and subtitle_language:
                    for lang_code in automatic_captions:
                        if lang_code.startswith(subtitle_language):
                            subtitle_download_link = automatic_captions[lang_code][-1][
                                "url"
                            ]
                            break
            except Exception:
                subtitle_download_link = None

            ydl.params.update(
                {
                    "paths": {
                        "home": str(video_work_dir),
                        "subtitle": str(video_work_dir / "subtitle"),
                        "thumbnail": str(video_work_dir),
                    },
                }
            )
            ydl.process_info(info_dict)

            video_file_path = Path(ydl.prepare_filename(info_dict))
            if not video_file_path.exists():
                # Fallback: pick largest media file in work dir
                media = sorted(
                    [
                        p
                        for p in video_work_dir.rglob("*")
                        if p.suffix.lower() in {".mp4", ".mkv", ".webm", ".flv", ".m4a"}
                        and not p.name.endswith(".part")
                    ],
                    key=lambda p: p.stat().st_size,
                    reverse=True,
                )
                video_file_path = media[0] if media else None
            else:
                video_file_path = str(video_file_path)

            if video_file_path is not None:
                video_file_path = str(video_file_path)

            subtitle_file_path = None
            for file in video_work_dir.glob("**/【下载字幕】*"):
                file_path = str(file)
                if subtitle_language and subtitle_language not in file_path:
                    logger.info("字幕语言错误，重新下载字幕: %s", subtitle_download_link)
                    os.remove(file_path)
                    if subtitle_download_link:
                        response = requests.get(subtitle_download_link, timeout=30)
                        file_path = str(
                            video_work_dir
                            / "subtitle"
                            / f"【下载字幕】{subtitle_language}.vtt"
                        )
                        if response.text:
                            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
                            Path(file_path).write_text(response.text, encoding="utf-8")
                            subtitle_file_path = file_path
                else:
                    subtitle_file_path = file_path
                break

            thumbnail_file_path = None
            for file in video_work_dir.glob("**/thumbnail*"):
                thumbnail_file_path = str(file)
                break

            logger.info("视频下载完成: %s", video_file_path)
            return video_file_path, subtitle_file_path, thumbnail_file_path, info_dict
