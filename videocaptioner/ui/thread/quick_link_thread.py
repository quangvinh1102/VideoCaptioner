"""Pipeline: download URL or local video → ASR → translate → optional dub."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from PyQt5.QtCore import QThread, pyqtSignal

from videocaptioner.core.asr.asr_data import ASRData
from videocaptioner.core.asr.transcribe import transcribe
from videocaptioner.core.dubbing import DubbingConfig, DubbingPipeline
from videocaptioner.core.entities import (
    SubtitleLayoutEnum,
    TranscribeConfig,
    TranscribeModelEnum,
)
from videocaptioner.core.translate.factory import TranslatorFactory
from videocaptioner.core.translate.types import TargetLanguage, TranslatorType
from videocaptioner.core.utils.logger import setup_logger
from videocaptioner.core.utils.video_utils import add_subtitles, video2audio
from videocaptioner.ui.thread.video_download_thread import VideoDownloadThread

logger = setup_logger("quick_link_thread")

def _cache_key_for_url(url: str) -> str:
    """Stable folder name per video URL (BV id / YouTube id / hash)."""
    raw = (url or "").strip()
    if not raw:
        return "unknown"
    # Bilibili: BV1xxxx or av123
    m = re.search(r"(BV[\w]+)", raw, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"(?:[?&]|&amp;)?aid=(\d+)|/av(\d+)", raw, re.IGNORECASE)
    if m:
        return f"av{m.group(1) or m.group(2)}"
    # YouTube
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    if "youtu.be" in host:
        vid = parsed.path.strip("/").split("/")[0]
        if vid:
            return f"yt_{vid}"
    if "youtube.com" in host or "youtube-nocookie.com" in host:
        qs = parse_qs(parsed.query)
        if qs.get("v"):
            return f"yt_{qs['v'][0]}"
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            return f"yt_{parts[1]}"
    digest = hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"u_{digest}"


_PROCESSED_NAME_MARKERS = (
    "_dubbed",
    "_dubbed_audio",
    "_burn",
    "_logo",
    "_vi",
    "_out",
    "preview_clip",
)


def _is_ascii_path(path: Path | str) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _copy_to_ascii_temp(src: Path, dest_dir: Path, name: str) -> Path:
    """Copy file to an ASCII-only path (ffmpeg filters break on Unicode paths)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    if dest.exists():
        dest.unlink()
    shutil.copy2(src, dest)
    return dest


def _move_result(src: Path, dest: Path) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    try:
        src.replace(dest)
    except OSError:
        shutil.copy2(src, dest)
        src.unlink(missing_ok=True)
    return str(dest)


class QuickLinkThread(QThread):
    """Run download (or local file) + translate (+ dub) in background."""

    progress = pyqtSignal(int, str)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        output_dir: str,
        target_language: TargetLanguage,
        voice: str,
        url: str = "",
        local_video: str | None = None,
        enable_dub: bool = True,
        mix_original_audio: bool = False,
        original_audio_volume: float = 0.2,
        original_audio_mode: str = "keep_bgm",
        burn_subtitles: bool = True,
        burn_style: dict | None = None,
        overlay_logo: bool = False,
        logo_path: str | None = None,
        logo_placement: dict | None = None,
        cookiefile: str | None = None,
        llm_api_key: str | None = None,
        llm_api_base: str | None = None,
        llm_model: str | None = None,
        use_ai: bool = False,
        use_chatgpt_web: bool = False,
        edge_rate: str = "+0%",
        edge_pitch: str = "+0Hz",
        provider: str = "edge",
        capcut_resource_id: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.url = (url or "").strip()
        self.local_video = (local_video or "").strip() or None
        self.output_dir = Path(output_dir)
        self.target_language = target_language
        self.voice = voice
        self.provider = provider or "edge"
        self.edge_rate = edge_rate or "+0%"
        self.edge_pitch = edge_pitch or "+0Hz"
        self.capcut_resource_id = capcut_resource_id or ""
        self.enable_dub = enable_dub
        self.mix_original_audio = bool(mix_original_audio)
        self.original_audio_volume = float(original_audio_volume)
        mode = (original_audio_mode or "").strip() or "keep_bgm"
        if mode not in {"replace", "keep_bgm", "mix", "keep_full"}:
            mode = "mix" if self.mix_original_audio else "replace"
        self.original_audio_mode = mode
        self.burn_subtitles = burn_subtitles
        from videocaptioner.ui.common.burn_subtitle_style import BurnSubtitleStyle

        self.burn_style = BurnSubtitleStyle.from_dict(burn_style)
        self.overlay_logo = bool(overlay_logo)
        self.logo_path = (logo_path or "").strip() or None
        self.logo_placement = dict(logo_placement) if logo_placement else None
        self.cookiefile = cookiefile
        self.llm_api_key = (llm_api_key or "").strip()
        self.llm_api_base = (llm_api_base or "").strip() or "https://api.openai.com/v1"
        self.llm_model = (llm_model or "").strip() or "gpt-4o-mini"
        self.use_ai = bool(use_ai and self.llm_api_key)
        self.use_chatgpt_web = use_chatgpt_web
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            work_dir = self.output_dir / "_work"
            work_dir.mkdir(parents=True, exist_ok=True)

            if self.use_ai:
                os.environ["OPENAI_API_KEY"] = self.llm_api_key
                os.environ["OPENAI_BASE_URL"] = self.llm_api_base

            if self.local_video:
                video_path = self._resolve_local_video()
            else:
                if not self.url:
                    raise RuntimeError("Thiếu link hoặc file video")
                video_path = self._download(work_dir)
            if self._cancelled:
                return

            subtitle_path = self._transcribe_and_translate(video_path, work_dir)
            if self._cancelled:
                return

            current_video = video_path
            if self.enable_dub:
                current_video = self._dub_audio(video_path, subtitle_path, work_dir)
                if self._cancelled:
                    return

            logger.info(
                "Export flags: burn=%s overlay_logo=%s logo=%s placement=%s",
                self.burn_subtitles,
                self.overlay_logo,
                self.logo_path,
                self.logo_placement,
            )
            if self.burn_subtitles:
                result_path = self._burn_vietnamese_subs(
                    current_video, subtitle_path, work_dir
                )
            elif self.overlay_logo and self.logo_path:
                result_path = self._export_with_logo(current_video, work_dir)
            else:
                result_path = self._export_video_without_burn(
                    current_video, work_dir
                )

            self.progress.emit(100, "Hoàn tất")
            self.finished_ok.emit(result_path)
        except Exception as exc:
            logger.exception("Quick link pipeline failed")
            self.failed.emit(str(exc))

    def _resolve_local_video(self) -> str:
        path = Path(self.local_video or "")
        if not path.is_file():
            raise RuntimeError(f"Không tìm thấy video: {path}")
        if path.suffix.lower() not in {
            ".mp4",
            ".mkv",
            ".webm",
            ".flv",
            ".mov",
            ".avi",
            ".m4v",
            ".ts",
            ".mpeg",
            ".mpg",
        }:
            raise RuntimeError(f"Định dạng không hỗ trợ: {path.suffix}")
        self.progress.emit(25, f"Dùng video máy: {path.name}")
        return str(path.resolve())

    def _download(self, work_dir: Path) -> str:
        """Download URL into a per-video cache folder (never reuse another link's file)."""
        cache_key = _cache_key_for_url(self.url)
        url_dir = work_dir / cache_key
        url_dir.mkdir(parents=True, exist_ok=True)
        marker = url_dir / "source.url"
        # Keep a record of the exact URL for this cache slot
        try:
            marker.write_text(self.url.strip() + "\n", encoding="utf-8")
        except OSError:
            pass

        # Resume only if this same URL (or same BV id folder) already has a media file
        existing = []
        for p in url_dir.rglob("*"):
            if p.suffix.lower() not in {".mp4", ".mkv", ".webm", ".flv"}:
                continue
            if p.name.endswith(".part"):
                continue
            lower = p.name.lower()
            if any(m in lower for m in _PROCESSED_NAME_MARKERS):
                continue
            if "ffmpeg_safe" in p.parts:
                continue
            if p.stat().st_size > 1_000_000:
                existing.append(p)
        if existing:
            # If marker URL differs wildly (rare hash collision), force re-download
            prev = ""
            try:
                prev = marker.read_text(encoding="utf-8").strip()
            except OSError:
                prev = ""
            same_id = _cache_key_for_url(prev) == cache_key if prev else True
            if same_id:
                best = max(existing, key=lambda p: p.stat().st_size)
                self.progress.emit(
                    25, f"Dùng video đã tải ({cache_key}): {best.name}"
                )
                logger.info(
                    "Resume download cache key=%s url=%s file=%s",
                    cache_key,
                    self.url,
                    best,
                )
                return str(best)

        self.progress.emit(2, f"Đang tải video ({cache_key})...")
        logger.info("Downloading url=%s → cache=%s", self.url, url_dir)
        downloader = VideoDownloadThread(
            self.url, str(url_dir), cookiefile=self.cookiefile
        )
        # Run download synchronously inside this worker thread
        error_box: list[str] = []
        result_box: list[str] = []

        def on_finished(path: str) -> None:
            result_box.append(path)

        def on_error(msg: str) -> None:
            error_box.append(msg)

        def on_progress(pct: int, msg: str) -> None:
            # Map download 0-100 → overall 2-25
            self.progress.emit(2 + int(pct * 0.23), msg)

        downloader.finished.connect(on_finished)
        downloader.error.connect(on_error)
        downloader.progress.connect(on_progress)
        downloader.run()  # synchronous (already in QThread)

        if error_box:
            raise RuntimeError(error_box[0])
        if not result_box:
            raise RuntimeError("Tải video thất bại: không có file đầu ra")
        return result_box[0]

    def _transcribe_and_translate(self, video_path: str, work_dir: Path) -> Path:
        self.progress.emit(28, "Đang trích xuất âm thanh...")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = tmp.name
        if not video2audio(video_path, audio_path):
            raise RuntimeError("Không trích xuất được âm thanh từ video")

        if self._cancelled:
            Path(audio_path).unlink(missing_ok=True)
            raise RuntimeError("Đã hủy")

        self.progress.emit(35, "Đang nhận diện giọng nói (ASR)...")

        def asr_cb(pct: int, msg: str) -> None:
            self.progress.emit(35 + int(pct * 0.25), f"ASR: {msg}")

        config = TranscribeConfig(
            transcribe_model=TranscribeModelEnum.BIJIAN,
            need_word_time_stamp=False,
        )
        asr_data: ASRData = transcribe(audio_path, config, callback=asr_cb)
        Path(audio_path).unlink(missing_ok=True)

        if self._cancelled:
            raise RuntimeError("Đã hủy")

        total_segs = max(len(asr_data.segments), 1)

        # Optional LLM polish before translate
        if self.use_ai:
            self.progress.emit(55, "AI đang tối ưu phụ đề...")
            done_opt = {"n": 0}

            def optimize_cb(result) -> None:
                # Optimizer passes List[SubtitleProcessData]
                n = len(result) if hasattr(result, "__len__") else 1
                done_opt["n"] += n
                pct = min(int(done_opt["n"] / total_segs * 100), 100)
                self.progress.emit(55 + int(pct * 0.07), f"AI tối ưu: {done_opt['n']}/{total_segs}")

            try:
                from videocaptioner.core.optimize.optimize import SubtitleOptimizer

                optimizer = SubtitleOptimizer(
                    thread_num=3,
                    batch_num=8,
                    model=self.llm_model,
                    custom_prompt="",
                    update_callback=optimize_cb,
                )
                asr_data = optimizer.optimize_subtitle(asr_data)
                asr_data.remove_punctuation()
            except Exception as exc:
                logger.warning("AI optimize failed, continue without it: %s", exc)
                self.progress.emit(60, f"Bỏ qua tối ưu AI ({exc})")

        self.progress.emit(62, f"Đang dịch sang {self.target_language.value}...")
        done_tr = {"n": 0}

        def translate_cb(result) -> None:
            # Translator passes List[SubtitleProcessData] per finished chunk
            n = len(result) if hasattr(result, "__len__") else 1
            done_tr["n"] += n
            pct = min(int(done_tr["n"] / total_segs * 100), 100)
            self.progress.emit(62 + int(pct * 0.18), f"Dịch: {done_tr['n']}/{total_segs}")

        translator = None
        last_err: Exception | None = None
        if self.use_ai:
            services = (TranslatorType.OPENAI, TranslatorType.GOOGLE, TranslatorType.BING)
        else:
            services = (TranslatorType.GOOGLE, TranslatorType.BING)

        # Nếu người dùng chọn ChatGPT Web translator từ GUI
        if hasattr(self, 'use_chatgpt_web') and self.use_chatgpt_web:
            services = (TranslatorType.CHATGPT_WEB,)

        asr_data_out = None
        for service in services:
            try:
                self.progress.emit(62, f"Dùng dịch vụ: {service.value}...")
                translator = TranslatorFactory.create_translator(
                    translator_type=service,
                    thread_num=2 if service == TranslatorType.GOOGLE else 3,
                    batch_num=8 if service == TranslatorType.OPENAI else 3,
                    target_language=self.target_language,
                    model=self.llm_model,
                    update_callback=translate_cb,
                )
            except Exception as exc:
                last_err = exc
                logger.warning("Translator %s unavailable: %s", service.value, exc)
                translator = None
                continue

            try:
                asr_data_out = translator.translate_subtitle(asr_data)
                break
            except Exception as exc:
                last_err = exc
                msg = str(exc)
                logger.warning(
                    "Translator %s failed mid-run, trying next: %s",
                    service.value,
                    exc,
                )
                # OpenRouter hết credit → chuyển Google/Bing miễn phí
                if "402" in msg or "credits" in msg.lower() or "max_tokens" in msg.lower():
                    self.progress.emit(
                        62,
                        f"AI hết credit/max_tokens — chuyển {service.value} → dịch vụ tiếp...",
                    )
                translator = None
                continue

        if asr_data_out is None:
            raise RuntimeError(
                "Không dịch được phụ đề.\n"
                "Nếu dùng OpenRouter: nạp credit tại https://openrouter.ai/settings/credits "
                "hoặc tắt AI để dùng Google miễn phí.\n"
                f"Lỗi cuối: {last_err}"
            )

        asr_data = asr_data_out
        asr_data.remove_punctuation()

        stem = Path(video_path).stem
        bilingual_path = work_dir / f"{stem}_vi.srt"
        translate_only_path = work_dir / f"{stem}_dub.srt"
        asr_data.save(str(bilingual_path), layout=SubtitleLayoutEnum.ORIGINAL_ON_TOP)
        asr_data.save(str(translate_only_path), layout=SubtitleLayoutEnum.ONLY_TRANSLATE)

        # Copy Vietnamese (+ bilingual) SRT to output root for the user
        final_srt = self.output_dir / f"{stem}.srt"
        final_srt.write_text(bilingual_path.read_text(encoding="utf-8"), encoding="utf-8")
        vi_only = self.output_dir / f"{stem}_vi_only.srt"
        vi_only.write_text(
            translate_only_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return translate_only_path

    def _dub_audio(self, video_path: str, subtitle_path: Path, work_dir: Path) -> str:
        self.progress.emit(82, "Đang ghép giọng (TTS)...")
        stem = Path(video_path).stem
        audio_out = work_dir / f"{stem}_dub.wav"
        video_dubbed = work_dir / f"{stem}_dubbed_audio{Path(video_path).suffix}"

        config = DubbingConfig(
            provider=self.provider,  # type: ignore[arg-type]
            api_key="",
            base_url="",
            model="edge-tts" if self.provider == "edge" else "capcut-tts",
            voice=self.voice,
            edge_rate=self.edge_rate,
            edge_pitch=self.edge_pitch,
            capcut_resource_id=self.capcut_resource_id,
            mix_original_audio=self.mix_original_audio,
            original_audio_volume=self.original_audio_volume,
            original_audio_mode=self.original_audio_mode,  # type: ignore[arg-type]
            dubbed_audio_volume=1.0,
            tts_workers=1,
            timeout=90,
        )

        def dub_cb(pct: int, msg: str) -> None:
            # Leave room for optional subtitle burn (82→94 or 82→100)
            span = 12 if self.burn_subtitles else 17
            self.progress.emit(82 + int(pct * span / 100), f"Dub: {msg}")

        result = DubbingPipeline(config).run(
            str(subtitle_path),
            str(audio_out),
            video_path=video_path,
            output_video_path=str(video_dubbed),
            text_track="auto",
            work_dir=str(work_dir / f"{stem}_parts"),
            callback=dub_cb,
        )
        out = result.video_path
        if out and Path(out).is_file() and Path(out).stat().st_size > 1000:
            return str(out)
        if video_dubbed.is_file() and video_dubbed.stat().st_size > 1000:
            return str(video_dubbed)
        raise RuntimeError(
            "Dub xong nhưng không có file video (chỉ có audio). "
            "Kiểm tra ffmpeg mux."
        )

    def _export_stem(self, video_path: str) -> str:
        stem = Path(video_path).stem
        if stem.endswith("_dubbed_audio"):
            return stem.replace("_dubbed_audio", "") + "_dubbed"
        if self.enable_dub:
            return stem + "_dubbed"
        return stem + "_out"

    def _safe_dir(self, work_dir: Path) -> Path:
        # Always use system temp (ASCII). work_dir often has Bilibili Chinese titles
        # and libass/ffmpeg filtergraphs break on non-ASCII paths.
        d = Path(tempfile.gettempdir()) / "vc_ffmpeg_safe"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _prepare_ffmpeg_inputs(
        self, video_path: str, work_dir: Path, *, logo_path: str | None = None
    ) -> tuple[str, str | None, Path]:
        """Return (video_for_ffmpeg, logo_for_ffmpeg, safe_dir) with ASCII paths."""
        safe = self._safe_dir(work_dir)
        src = Path(video_path)
        if _is_ascii_path(src):
            video_ff = str(src)
        else:
            video_ff = str(
                _copy_to_ascii_temp(src, safe, f"input{src.suffix.lower() or '.mp4'}")
            )
            logger.info("Copied video to ASCII temp for ffmpeg: %s", video_ff)

        logo_ff = None
        if logo_path:
            logo_src = Path(logo_path)
            if not logo_src.is_file():
                raise FileNotFoundError(f"Không tìm thấy logo: {logo_src}")
            if _is_ascii_path(logo_src):
                logo_ff = str(logo_src)
            else:
                logo_ff = str(
                    _copy_to_ascii_temp(
                        logo_src, safe, f"logo{logo_src.suffix.lower() or '.png'}"
                    )
                )
        return video_ff, logo_ff, safe

    def _export_video_without_burn(self, video_path: str, work_dir: Path) -> str:
        """Copy dubbed/source video to output folder without burning subtitles."""
        self.progress.emit(96, "Xuất video (không cháy sub)...")
        out_stem = self._export_stem(video_path)
        final_out = self.output_dir / f"{out_stem}{Path(video_path).suffix}"
        src = Path(video_path)
        if src.resolve() == final_out.resolve():
            return str(final_out)
        if final_out.exists():
            final_out.unlink()
        shutil.copy2(src, final_out)
        self.progress.emit(99, f"Đã lưu: {final_out.name} (chỉ giọng, không sub)")
        return str(final_out)

    def _export_with_logo(self, video_path: str, work_dir: Path) -> str:
        """Export video with logo overlay only (no subtitle burn)."""
        from videocaptioner.core.utils.logo_overlay import overlay_logo_on_video

        if not self.logo_path:
            raise RuntimeError("Đã bật đè logo nhưng thiếu đường dẫn logo")

        self.progress.emit(94, "Đang đè logo che watermark...")
        out_stem = self._export_stem(video_path)
        final_out = self.output_dir / f"{out_stem}{Path(video_path).suffix}"
        video_ff, logo_ff, safe = self._prepare_ffmpeg_inputs(
            video_path, work_dir, logo_path=self.logo_path
        )
        temp_out = safe / f"logo_out{Path(video_path).suffix.lower() or '.mp4'}"

        def cb(pct: str, msg: str = "") -> None:
            try:
                p = int(float(pct))
            except ValueError:
                p = 0
            self.progress.emit(94 + int(max(0, min(p, 100)) * 0.05), f"Logo: {msg or pct}%")

        overlay_logo_on_video(
            video_ff,
            logo_ff or self.logo_path,
            str(temp_out),
            placement=self.logo_placement,
            progress_callback=cb,
        )
        if not temp_out.is_file() or temp_out.stat().st_size < 1000:
            raise RuntimeError("ffmpeg đè logo xong nhưng không có file đầu ra")
        result = _move_result(temp_out, final_out)
        self.progress.emit(99, f"Đã đè logo: {final_out.name}")
        return result

    def _burn_vietnamese_subs(
        self, video_path: str, subtitle_path: Path, work_dir: Path
    ) -> str:
        """Hard-burn Vietnamese (+ optional logo) onto video."""
        self.progress.emit(94, "Đang cháy phụ đề Việt (+ logo nếu bật)...")
        stem = Path(video_path).stem
        if stem.endswith("_dubbed_audio"):
            out_stem = stem.replace("_dubbed_audio", "") + "_dubbed"
        else:
            out_stem = stem + "_vi"
        final_out = self.output_dir / f"{out_stem}{Path(video_path).suffix}"

        video_ff, logo_ff, safe = self._prepare_ffmpeg_inputs(
            video_path,
            work_dir,
            logo_path=self.logo_path if self.overlay_logo else None,
        )
        temp_out = safe / f"burn_out{Path(video_path).suffix.lower() or '.mp4'}"

        def burn_cb(pct: str, msg: str = "") -> None:
            try:
                p = int(float(pct))
            except ValueError:
                p = 0
            self.progress.emit(
                94 + int(max(0, min(p, 100)) * 0.05),
                f"Sub: {msg or pct}%",
            )

        errors: list[str] = []
        try:
            ass_path = self._build_vi_cover_ass(video_ff, subtitle_path, safe)
            if self.overlay_logo and (logo_ff or self.logo_path):
                from videocaptioner.core.utils.logo_overlay import overlay_logo_on_video

                logger.info(
                    "Burn+logo: video=%s logo=%s ass=%s → %s",
                    video_ff,
                    logo_ff or self.logo_path,
                    ass_path,
                    temp_out,
                )
                overlay_logo_on_video(
                    video_ff,
                    logo_ff or self.logo_path or "",
                    str(temp_out),
                    placement=self.logo_placement,
                    ass_path=str(ass_path),
                    progress_callback=burn_cb,
                )
            else:
                logger.info("Burn ASS only: video=%s ass=%s → %s", video_ff, ass_path, temp_out)
                self._ffmpeg_burn_ass(
                    video_ff, ass_path, temp_out, progress_callback=burn_cb
                )
            if temp_out.is_file() and temp_out.stat().st_size > 1000:
                result = _move_result(temp_out, final_out)
                self.progress.emit(99, f"Đã cháy sub Việt: {final_out.name}")
                return result
            errors.append("ffmpeg không tạo được file burn")
        except Exception as exc:
            logger.exception("Burn Vietnamese subtitles failed")
            errors.append(str(exc))
            self.progress.emit(96, f"Cháy ASS lỗi — thử SRT: {exc}")
            try:
                # Fallback: burn SRT without logo first, then logo if needed
                srt_tmp = safe / "burn_srt.mp4"
                add_subtitles(
                    video_ff,
                    str(subtitle_path),
                    str(srt_tmp),
                    soft_subtitle=False,
                    crf=23,
                    preset="fast",
                    progress_callback=burn_cb,
                )
                if self.overlay_logo and (logo_ff or self.logo_path):
                    from videocaptioner.core.utils.logo_overlay import (
                        overlay_logo_on_video,
                    )

                    overlay_logo_on_video(
                        str(srt_tmp),
                        logo_ff or self.logo_path or "",
                        str(temp_out),
                        placement=self.logo_placement,
                        progress_callback=burn_cb,
                    )
                else:
                    if temp_out.exists():
                        temp_out.unlink()
                    srt_tmp.replace(temp_out)
                if temp_out.is_file() and temp_out.stat().st_size > 1000:
                    result = _move_result(temp_out, final_out)
                    self.progress.emit(99, f"Đã cháy sub (fallback): {final_out.name}")
                    return result
                errors.append("fallback SRT cũng không ra file")
            except Exception as exc2:
                logger.exception("Fallback burn also failed")
                errors.append(str(exc2))

        raise RuntimeError(
            "Không cháy được phụ đề/logo vào video. "
            + " | ".join(errors[-3:])
        )

    def _build_vi_cover_ass(
        self, video_path: str, subtitle_path: Path, work_dir: Path
    ) -> Path:
        """ASS: customizable font/colors + BorderStyle=3 + \\pos from preview."""
        from videocaptioner.core.asr.asr_data import ASRData
        from videocaptioner.core.utils.video_utils import get_video_info
        from videocaptioner.ui.common.burn_subtitle_style import (
            ass_pos_override,
            build_ass_style_block,
            inject_ass_pos,
        )

        info = get_video_info(video_path)
        width = (info.width if info and info.width else 1280) or 1280
        height = (info.height if info and info.height else 720) or 720
        style_str = build_ass_style_block(self.burn_style, height)

        asr = ASRData.from_subtitle_file(str(subtitle_path))
        if not asr.segments:
            raise RuntimeError(f"File phụ đề trống: {subtitle_path}")

        # translate-only SRT → text field holds Vietnamese; ONLY_ORIGINAL is correct
        ass_path = work_dir / "vi_cover.ass"
        content = asr.to_ass(
            style_str=style_str,
            layout=SubtitleLayoutEnum.ONLY_ORIGINAL,
            save_path=None,
            video_width=width,
            video_height=height,
        )
        pos_tag = ass_pos_override(self.burn_style, width, height)
        content = inject_ass_pos(content, pos_tag)
        # utf-8-sig for ffmpeg/libass on Windows
        ass_path.write_text(content, encoding="utf-8-sig")
        logger.info(
            "Built ASS: %s (%d segs, pos=%s)",
            ass_path,
            len(asr.segments),
            pos_tag,
        )
        return ass_path

    def _ffmpeg_burn_ass(
        self,
        video_path: str,
        ass_path: Path,
        output_path: Path,
        progress_callback=None,
    ) -> None:
        """Burn ASS only (opaque box around text — no full-width black bar)."""
        import subprocess

        # Ensure ASS is on an ASCII path for the filtergraph
        if not _is_ascii_path(ass_path):
            safe_ass = Path(tempfile.gettempdir()) / "vc_vi_cover.ass"
            shutil.copy2(ass_path, safe_ass)
            ass_path = safe_ass

        ass_escaped = ass_path.resolve().as_posix().replace(":", r"\:")
        vf = f"ass='{ass_escaped}'"

        # Software decode only — CUDA hwaccel + ass filter breaks on AV1 (Bilibili)
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vf",
            f"{vf},format=yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "high",
            "-crf",
            "23",
            "-preset",
            "fast",
            "-movflags",
            "+faststart",
            "-y",
            str(output_path),
        ]
        logger.info("Burn VI ASS: %s", subprocess.list2cmdline(cmd))

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
                progress_callback(str(round(cur / total_duration * 100)), "đang cháy sub")
        if process.wait() != 0:
            raise RuntimeError(f"ffmpeg burn failed: {''.join(err_tail)[-500:]}")
        if progress_callback:
            progress_callback("100", "xong")
