"""Shared yt-dlp download helpers (cookies, Bilibili headers, etc.)."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from videocaptioner.config import APPDATA_PATH, ROOT_PATH
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("download_helper")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

BROWSER_CANDIDATES = ("chrome", "edge", "firefox", "brave", "opera")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text or "").strip()


def default_cookie_path() -> Path:
    return APPDATA_PATH / "cookies.txt"


def resolve_cookie_file(cookiefile: Optional[str] = None) -> Optional[Path]:
    """Find cookies.txt from UI path, AppData, or next to the exe."""
    candidates: list[Path] = []
    if cookiefile:
        candidates.append(Path(cookiefile))
    candidates.extend(
        [
            default_cookie_path(),
            ROOT_PATH / "cookies.txt",
            ROOT_PATH / "AppData" / "cookies.txt",
            Path.home() / "VideoCaptioner" / "cookies.txt",
        ]
    )
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.resolve()) if path.exists() else str(path)
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            if path.is_file() and path.stat().st_size > 0:
                return path
        except OSError:
            continue
    return None


def browser_cookies_supported() -> bool:
    """cookiesfrombrowser uses Windows DPAPI — broken under PyInstaller packaged exe.

    See https://github.com/yt-dlp/yt-dlp/issues/10927
    """
    if getattr(sys, "frozen", False):
        return False
    return True


def resolve_ffmpeg_exe() -> Optional[Path]:
    """Find ffmpeg.exe even when the current process PATH is stale."""
    which = shutil.which("ffmpeg")
    if which:
        return Path(which)

    candidates: list[Path] = []
    local = Path.home() / "AppData" / "Local"
    candidates.extend(
        [
            local / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe",
            Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
            Path.home() / "scoop" / "shims" / "ffmpeg.exe",
        ]
    )
    # Bundled desktop runtime / resource bin
    for base in (ROOT_PATH, Path(getattr(sys, "_MEIPASS", ROOT_PATH))):
        candidates.append(Path(base) / "resource" / "bin" / "ffmpeg.exe")
        candidates.append(Path(base) / "_internal" / "resource" / "bin" / "ffmpeg.exe")

    winget_root = local / "Microsoft" / "WinGet" / "Packages"
    if winget_root.exists():
        candidates.extend(winget_root.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffmpeg.exe"))
        candidates.extend(winget_root.glob("Gyan.FFmpeg*/**/ffmpeg.exe"))

    for path in candidates:
        if path.is_file():
            return path
    return None


def ensure_ffmpeg_on_path() -> Optional[str]:
    """Ensure ffmpeg is discoverable; return bin directory if found."""
    exe = resolve_ffmpeg_exe()
    if not exe:
        return None
    bin_dir = str(exe.parent)
    path_env = os.environ.get("PATH", "")
    if bin_dir.lower() not in path_env.lower():
        os.environ["PATH"] = bin_dir + os.pathsep + path_env
        logger.info("Prepended ffmpeg to PATH: %s", bin_dir)
    return bin_dir


def bilibili_http_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
    }


def is_bilibili_url(url: str) -> bool:
    lower = (url or "").lower()
    return "bilibili.com" in lower or "b23.tv" in lower


def apply_auth_opts(
    ydl_opts: dict[str, Any],
    url: str,
    cookiefile: Optional[str] = None,
    *,
    allow_browser_cookies: bool = True,
) -> dict[str, Any]:
    """Attach cookies / browser cookies / site headers for download.

    Priority:
    1. Explicit cookiefile / resolved cookies.txt
    2. For Bilibili (dev only): cookiesfrombrowser — skipped in frozen exe (DPAPI)
    """
    opts = dict(ydl_opts)

    if is_bilibili_url(url):
        headers = dict(opts.get("http_headers") or {})
        headers.update(bilibili_http_headers())
        opts["http_headers"] = headers

    cookie_path = resolve_cookie_file(cookiefile)
    if cookie_path is not None:
        logger.info("Using cookie file: %s", cookie_path)
        opts["cookiefile"] = str(cookie_path)
        opts.pop("cookiesfrombrowser", None)
        return opts

    if (
        allow_browser_cookies
        and browser_cookies_supported()
        and is_bilibili_url(url)
    ):
        opts.setdefault("cookiesfrombrowser", (BROWSER_CANDIDATES[0],))
        logger.info(
            "Auth fallback cookiesfrombrowser=%s",
            opts.get("cookiesfrombrowser"),
        )
    else:
        opts.pop("cookiesfrombrowser", None)
        if is_bilibili_url(url) and getattr(sys, "frozen", False):
            logger.info(
                "Skipping cookiesfrombrowser in packaged exe (DPAPI). "
                "Place cookies.txt next to the exe or in AppData."
            )

    return opts


def apply_ffmpeg_opts(ydl_opts: dict[str, Any]) -> dict[str, Any]:
    """Tell yt-dlp where ffmpeg lives so merge works even if PATH is stale."""
    opts = dict(ydl_opts)
    ffmpeg_dir = ensure_ffmpeg_on_path()
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir
    else:
        # Prefer a single pre-merged stream if ffmpeg is truly missing
        opts["format"] = (
            "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best"
        )
        logger.warning("ffmpeg not found; preferring single-file formats")
    return opts


def is_dpapi_cookie_error(exc: BaseException | str) -> bool:
    msg = str(exc).lower()
    return any(
        x in msg
        for x in (
            "dpapi",
            "failed to decrypt",
            "could not copy",
            "failed to decrypt with dpapi",
        )
    )


def friendly_download_error(exc: BaseException, url: str = "") -> str:
    raw = strip_ansi(str(exc))
    if is_dpapi_cookie_error(raw):
        cookie = default_cookie_path()
        beside = ROOT_PATH / "cookies.txt"
        return (
            "Không đọc được cookies từ trình duyệt (lỗi DPAPI — bản .exe thường bị).\n\n"
            "Cách khắc phục:\n"
            "1. Export cookies.txt bằng extension «Get cookies.txt LOCALLY» trên trang Bilibili.\n"
            f"2. Đặt file vào một trong các chỗ:\n"
            f"   • {beside}\n"
            f"   • {cookie}\n"
            "   hoặc chọn file ở ô Cookies trên giao diện.\n"
            "3. Bấm «Xem trước» / Bắt đầu lại (không cần lấy cookie từ Chrome).\n\n"
            f"Chi tiết: {raw}"
        )
    if "ffmpeg is not installed" in raw.lower() or (
        "merging of multiple formats" in raw.lower() and "ffmpeg" in raw.lower()
    ):
        return (
            "yt-dlp cần FFmpeg để ghép video+audio.\n\n"
            "FFmpeg có thể đã cài nhưng app chưa thấy PATH.\n"
            "Hãy đóng GUI hoàn toàn rồi mở lại:\n"
            "  uv run videocaptioner gui\n\n"
            f"Chi tiết: {raw}"
        )
    if any(
        x in raw.lower()
        for x in ("more expected", "bytes read", "got error")
    ):
        return (
            "Tải gần xong nhưng mạng/CDN Bilibili bị đứt giữa chừng.\n\n"
            "Đã bật tự tiếp tục tải dở — hãy Bắt đầu lại (sẽ resume).\n"
            "Nếu vẫn lỗi: thử mạng ổn định hơn / VPN gần Trung Quốc.\n\n"
            f"Chi tiết: {raw}"
        )
    if "412" in raw or "Precondition Failed" in raw or (
        is_bilibili_url(url) and ("403" in raw or "Forbidden" in raw)
    ):
        cookie = default_cookie_path()
        beside = ROOT_PATH / "cookies.txt"
        return (
            "Bilibili chặn tải (HTTP 412/403). Cần file cookies.txt.\n\n"
            "Cách khắc phục (khuyến nghị):\n"
            "1. Mở Chrome/Edge → vào https://www.bilibili.com (nên đăng nhập).\n"
            "2. Cài extension: Get cookies.txt LOCALLY\n"
            "   https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc\n"
            "3. Trên trang Bilibili, bấm extension → Export → lưu cookies.txt\n"
            f"4. Đặt file vào:\n   {beside}\n   hoặc {cookie}\n"
            "   hoặc chọn file trên giao diện (ô Cookies Bilibili).\n"
            "5. Đóng & mở lại app, rồi bấm Bắt đầu lại.\n\n"
            f"Chi tiết: {raw}"
        )
    return raw
