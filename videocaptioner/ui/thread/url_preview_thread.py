"""Fetch a real video frame for logo/sub preview (not cover thumbnail)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests
import yt_dlp
from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.utils.download_helper import (
    apply_auth_opts,
    apply_ffmpeg_opts,
    bilibili_http_headers,
    friendly_download_error,
    is_bilibili_url,
)
from videocaptioner.core.utils.logger import setup_logger

logger = setup_logger("url_preview_thread")

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _pick_thumbnail_url(info: dict) -> Optional[str]:
    thumbs = info.get("thumbnails") or []
    best_url = None
    best_area = -1
    for t in thumbs:
        if not isinstance(t, dict):
            continue
        url = t.get("url")
        if not url:
            continue
        w = int(t.get("width") or 0)
        h = int(t.get("height") or 0)
        area = w * h if w and h else int(t.get("preference") or 0)
        if area >= best_area:
            best_area = area
            best_url = url
    if best_url:
        return best_url
    return info.get("thumbnail") or None


def _guess_ext(url: str, content_type: str = "") -> str:
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    return ".jpg"


def _preview_seek_sec(info: dict) -> float:
    """Seek into the episode so burned-in sub/watermark usually visible."""
    try:
        duration = float(info.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        return 8.0
    # ~25% into the video, but keep away from cold open / credits
    seek = duration * 0.25
    seek = max(4.0, min(seek, max(duration - 4.0, 1.0)))
    return float(seek)


def _pick_stream_url(info: dict) -> Optional[tuple[str, dict[str, str]]]:
    """Pick a modest-resolution video URL for ffmpeg frame grab."""
    formats = list(info.get("formats") or [])
    scored: list[tuple[int, dict[str, Any]]] = []
    for fmt in formats:
        if not isinstance(fmt, dict):
            continue
        url = fmt.get("url")
        if not url:
            continue
        vcodec = (fmt.get("vcodec") or "").lower()
        if vcodec in {"", "none"}:
            continue
        height = int(fmt.get("height") or 0)
        # Prefer 360–720p: enough detail for logo/sub, still fast
        if height and height > 900:
            score = 1000 + height  # last resort
        elif 360 <= height <= 720:
            score = height
        elif height:
            score = 200 + height
        else:
            score = 50
        # Prefer mp4 / progressive when possible
        ext = (fmt.get("ext") or "").lower()
        if ext == "mp4":
            score += 30
        if fmt.get("acodec") not in (None, "none"):
            score += 5  # progressive slightly nicer for ffmpeg
        scored.append((score, fmt))

    if not scored:
        return None
    scored.sort(key=lambda x: x[0])
    # Among good scores, take the best under 900 preference band first
    under = [x for x in scored if x[0] < 1000]
    chosen = (under[-1] if under else scored[0])[1]
    http_headers = dict(chosen.get("http_headers") or {})
    return str(chosen["url"]), http_headers


def _ffmpeg_frame_from_url(
    stream_url: str,
    out_path: Path,
    *,
    seek_sec: float,
    extra_headers: dict[str, str] | None = None,
) -> None:
    headers = dict(extra_headers or {})
    header_blob = "".join(f"{k}: {v}\r\n" for k, v in headers.items()) if headers else ""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if header_blob:
        cmd.extend(["-headers", header_blob])
    cmd.extend(
        [
            "-ss",
            f"{max(0.0, seek_sec):.2f}",
            "-i",
            stream_url,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-update",
            "1",
            str(out_path),
        ]
    )
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0 or not out_path.is_file() or out_path.stat().st_size < 200:
        err = (result.stderr or result.stdout or "ffmpeg failed").strip()
        raise RuntimeError(err[:400] or "ffmpeg không lấy được frame")


def _ffmpeg_frame_from_file(video_path: Path, out_path: Path, *, seek_sec: float) -> None:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{max(0.0, seek_sec):.2f}",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-update",
        "1",
        str(out_path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
    )
    if result.returncode != 0 or not out_path.is_file() or out_path.stat().st_size < 200:
        err = (result.stderr or result.stdout or "ffmpeg failed").strip()
        raise RuntimeError(err[:400] or "ffmpeg không lấy được frame từ clip")


def _download_short_clip(
    page_url: str,
    out_dir: Path,
    *,
    seek_sec: float,
    cookiefile: Optional[str],
) -> Path:
    """Download ~3s around seek so we can extract a real frame (yt-dlp handles auth)."""
    try:
        from yt_dlp.utils import download_range_func
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("yt-dlp thiếu download_range_func") from exc

    start = float(max(0.0, seek_sec))
    end = float(start + 3.0)
    out_tmpl = str(out_dir / "preview_clip.%(ext)s")
    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": out_tmpl,
        # Small video-only / low-res first for speed
        "format": (
            "bv*[height<=480][ext=mp4]/bv*[height<=480]/"
            "b[height<=480]/wv*/w"
        ),
        # API expects list of (start, end) tuples — not dicts
        "download_ranges": download_range_func(None, [(start, end)]),
        "force_keyframes_at_cuts": True,
        "overwrites": True,
    }
    ydl_opts = apply_auth_opts(
        ydl_opts, page_url, cookiefile, allow_browser_cookies=False
    )
    ydl_opts = apply_ffmpeg_opts(ydl_opts)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([page_url])

    clips = sorted(
        out_dir.glob("preview_clip.*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    clips = [
        p
        for p in clips
        if p.suffix.lower()
        not in {".jpg", ".png", ".webp", ".json", ".vtt", ".srt", ".part"}
    ]
    if not clips:
        raise RuntimeError("Tải clip preview thất bại (không thấy file)")
    return clips[0]


def _download_thumbnail(info: dict, page_url: str) -> Path:
    thumb_url = _pick_thumbnail_url(info)
    if not thumb_url:
        raise RuntimeError("Không có thumbnail dự phòng")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
    }
    if is_bilibili_url(page_url):
        headers.update(bilibili_http_headers())
    else:
        headers["Referer"] = page_url

    resp = requests.get(thumb_url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.content
    if not data or len(data) < 200:
        raise RuntimeError("Ảnh thumbnail trống")
    ext = _guess_ext(thumb_url, resp.headers.get("Content-Type", ""))
    out = Path(tempfile.gettempdir()) / f"vc_url_preview_thumb{ext}"
    out.write_bytes(data)
    return out


class UrlPreviewThread(QThread):
    """Grab a real in-video frame for placing logo / burned subtitles."""

    finished_ok = pyqtSignal(str, str)  # image_path, title
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, url: str, cookiefile: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.url = (url or "").strip()
        self.cookiefile = cookiefile

    def run(self) -> None:
        work: Path | None = None
        try:
            if not (self.url.startswith("http://") or self.url.startswith("https://")):
                raise ValueError("Link phải bắt đầu bằng http:// hoặc https://")

            self.status.emit("Đang lấy thông tin video...")
            ydl_opts: dict[str, Any] = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
            }

            info = None
            last_extract_err: Exception | None = None
            # 1) cookie file / headers  2) no browser cookies (exe-safe)
            # 3) browser cookies only in non-frozen dev if needed
            from videocaptioner.core.utils.download_helper import (
                browser_cookies_supported,
                is_dpapi_cookie_error,
            )

            attempt_flags = [
                {"allow_browser_cookies": False},
            ]
            if browser_cookies_supported():
                attempt_flags.append({"allow_browser_cookies": True})

            for flags in attempt_flags:
                try:
                    opts = apply_auth_opts(
                        dict(ydl_opts),
                        self.url,
                        self.cookiefile,
                        allow_browser_cookies=flags["allow_browser_cookies"],
                    )
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(self.url, download=False)
                    if info:
                        break
                except Exception as exc:
                    last_extract_err = exc
                    if is_dpapi_cookie_error(exc):
                        logger.warning(
                            "Browser cookies DPAPI failed — retry without: %s", exc
                        )
                        continue
                    # Other errors: still try next auth mode once
                    logger.warning("extract_info failed (%s): %s", flags, exc)
                    continue

            if not info:
                if last_extract_err:
                    raise last_extract_err
                raise RuntimeError("Không lấy được thông tin video")

            title = str(info.get("title") or info.get("id") or "video").strip()
            seek = _preview_seek_sec(info)
            out = Path(tempfile.gettempdir()) / "vc_url_preview_frame.jpg"
            if out.exists():
                try:
                    out.unlink()
                except OSError:
                    pass

            # 1) Fast path: ffmpeg seek on direct stream URL (~1 frame, no full file)
            frame_ok = False
            last_err = ""
            picked = _pick_stream_url(info)
            if picked:
                stream_url, stream_headers = picked
                headers = dict(stream_headers)
                if is_bilibili_url(self.url):
                    headers.update(bilibili_http_headers())
                try:
                    self.status.emit(
                        f"Đang lấy 1 frame thật (~{seek:.0f}s): {title[:50]}..."
                    )
                    _ffmpeg_frame_from_url(
                        stream_url,
                        out,
                        seek_sec=seek,
                        extra_headers=headers,
                    )
                    frame_ok = True
                    logger.info("Preview frame from stream URL: %s", out)
                except Exception as exc:
                    last_err = str(exc)
                    logger.warning("Stream frame grab failed: %s", exc)

            # 2) Fallback: download ~3s clip via yt-dlp (better with cookies/CDN)
            if not frame_ok:
                try:
                    self.status.emit(
                        f"Tải clip ngắn để lấy frame (~{seek:.0f}s)..."
                    )
                    work = Path(tempfile.mkdtemp(prefix="vc_url_preview_"))
                    clip = _download_short_clip(
                        self.url,
                        work,
                        seek_sec=seek,
                        cookiefile=self.cookiefile,
                    )
                    _ffmpeg_frame_from_file(clip, out, seek_sec=0.3)
                    frame_ok = True
                    logger.info("Preview frame from short clip: %s", out)
                except Exception as exc:
                    last_err = str(exc)
                    logger.warning("Short-clip preview failed: %s", exc)

            if frame_ok and out.is_file():
                self.finished_ok.emit(str(out), title)
                return

            # 3) Last resort: cover thumbnail (warn via title prefix in log)
            self.status.emit("Không lấy được frame — dùng ảnh bìa (kém chính xác)...")
            thumb = _download_thumbnail(info, self.url)
            logger.warning(
                "Fell back to thumbnail after frame failures: %s", last_err or "unknown"
            )
            self.finished_ok.emit(
                str(thumb),
                f"[ảnh bìa] {title}",
            )
        except Exception as exc:
            logger.exception("URL preview failed: %s", exc)
            self.failed.emit(friendly_download_error(exc, self.url))
        finally:
            if work and work.is_dir():
                shutil.rmtree(work, ignore_errors=True)
