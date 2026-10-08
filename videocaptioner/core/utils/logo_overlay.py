"""Overlay a PNG logo onto video at a user-chosen position."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.video_utils import get_video_info

logger = setup_logger("logo_overlay")


def default_logo_path() -> Path:
    """Prefer project / bundled work-dir/Logo/logoYT.png."""
    import sys

    try:
        from videocaptioner.config import ROOT_PATH, WORK_PATH
    except Exception:
        ROOT_PATH = Path(__file__).resolve().parents[3]
        WORK_PATH = ROOT_PATH / "work-dir"

    root = Path(__file__).resolve().parents[3]
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ROOT_PATH))
        candidates.extend(
            [
                meipass / "work-dir" / "Logo" / "logoYT.png",
                meipass / "Logo" / "logoYT.png",
            ]
        )
    candidates.extend(
        [
            ROOT_PATH / "work-dir" / "Logo" / "logoYT.png",
            ROOT_PATH / "Logo" / "logoYT.png",
            WORK_PATH / "Logo" / "logoYT.png",
            root / "work-dir" / "Logo" / "logoYT.png",
            root / "Logo" / "logoYT.png",
            Path.cwd() / "work-dir" / "Logo" / "logoYT.png",
            Path.cwd() / "Logo" / "logoYT.png",
        ]
    )
    for p in candidates:
        if p.is_file():
            return p
    return candidates[0]


def extract_video_frame(video_path: str, output_png: str, *, time_sec: float = 1.0) -> Path:
    """Grab one frame for placement preview."""
    out = Path(output_png)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(max(0.0, time_sec)),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(out),
    ]
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    return out


def crop_logo_content(logo_path: str, output_png: str | None = None) -> Path:
    """Crop visible logo artwork (ignore near-empty transparent canvas)."""
    from PIL import Image

    src = Path(logo_path)
    im = Image.open(src).convert("RGBA")
    pixels = im.load()
    w, h = im.size
    min_x, min_y, max_x, max_y = w, h, 0, 0
    found = False
    # subsample for speed on large canvases
    step = 2 if max(w, h) > 800 else 1
    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b, a = pixels[x, y]
            if a > 20 and (r + g + b) > 40:
                found = True
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if not found:
        bbox = im.getbbox()
        if not bbox:
            return src
        cropped = im.crop(bbox)
    else:
        # pad a little + expand for subsample
        pad = 8
        box = (
            max(0, min_x - pad),
            max(0, min_y - pad),
            min(w, max_x + pad + step),
            min(h, max_y + pad + step),
        )
        cropped = im.crop(box)

    if output_png:
        out = Path(output_png)
    else:
        out = Path(tempfile.gettempdir()) / f"vc_logo_crop_{src.stem}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out)
    return out


def overlay_logo_on_video(
    video_path: str,
    logo_path: str,
    output_path: str,
    *,
    placement: dict | None = None,
    ass_path: str | None = None,
    progress_callback: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Burn logo at relative placement {x_pct,y_pct,w_pct} (+ optional ASS)."""
    video = Path(video_path)
    logo = Path(logo_path)
    out = Path(output_path)
    if not video.is_file():
        raise FileNotFoundError(f"Video không tồn tại: {video}")
    if not logo.is_file():
        raise FileNotFoundError(f"Logo không tồn tại: {logo}")

    info = get_video_info(str(video))
    width = int((info.width if info and info.width else 1280) or 1280)
    height = int((info.height if info and info.height else 720) or 720)
    out.parent.mkdir(parents=True, exist_ok=True)

    place = placement or {"x_pct": 0.68, "y_pct": 0.02, "w_pct": 0.28}
    x_pct = max(0.0, min(0.95, float(place.get("x_pct", 0.68))))
    y_pct = max(0.0, min(0.95, float(place.get("y_pct", 0.02))))
    w_pct = max(0.05, min(0.95, float(place.get("w_pct", 0.28))))

    logo_w = max(16, int(width * w_pct))
    x = int(width * x_pct)
    y = int(height * y_pct)
    # keep inside frame
    x = max(0, min(width - 8, x))
    y = max(0, min(height - 8, y))

    logo_chain = f"[1:v]format=rgba,scale={logo_w}:-1[lg]"
    # format=yuv420p: Windows Media Player / nhiều player không mở được yuv444p
    overlay = f"[0:v][lg]overlay={x}:{y}:format=auto[vtmp];[vtmp]format=yuv420p[vout]"

    if ass_path:
        ass_file = Path(ass_path)
        # libass filtergraph breaks on non-ASCII paths (Bilibili titles, etc.)
        try:
            str(ass_file.resolve()).encode("ascii")
        except UnicodeEncodeError:
            safe_ass = Path(tempfile.gettempdir()) / "vc_overlay_cover.ass"
            shutil.copy2(ass_file, safe_ass)
            ass_file = safe_ass
        ass_escaped = ass_file.resolve().as_posix().replace(":", r"\:")
        filter_complex = (
            f"{logo_chain};"
            f"[0:v][lg]overlay={x}:{y}:format=auto[vmid];"
            f"[vmid]ass='{ass_escaped}',format=yuv420p[vout]"
        )
    else:
        filter_complex = f"{logo_chain};{overlay}"

    # Do NOT use -hwaccel cuda here: AV1/Bilibili + software filters
    # (overlay/ass) with CUDA decode often yields frame=0 / exit 69.
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-i",
        str(logo),
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-crf",
        "23",
        "-preset",
        "fast",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(out),
    ]
    logger.info("Logo overlay: %s", subprocess.list2cmdline(cmd))
    _run_ffmpeg(cmd, progress_callback)


def _run_ffmpeg(
    cmd: list[str],
    progress_callback: Optional[Callable[[str, str], None]],
) -> None:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        ),
    )
    total_duration = None
    err_tail: list[str] = []
    while True:
        line = process.stderr.readline() if process.stderr else ""
        if not line and process.poll() is not None:
            break
        if line:
            err_tail.append(line)
            if len(err_tail) > 40:
                err_tail.pop(0)
        if not progress_callback or not line:
            continue
        if total_duration is None:
            m = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
            if m:
                h, mi, s = map(float, m.groups())
                total_duration = h * 3600 + mi * 60 + s
        tm = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
        if tm and total_duration:
            h, mi, s = map(float, tm.groups())
            cur = h * 3600 + mi * 60 + s
            progress_callback(
                str(round(cur / total_duration * 100)), "đang đè logo"
            )
    if process.wait() != 0:
        raise RuntimeError(f"ffmpeg logo overlay failed: {''.join(err_tail)[-500:]}")
    if progress_callback:
        progress_callback("100", "xong")
