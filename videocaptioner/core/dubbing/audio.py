"""Audio helpers for dubbing timeline assembly."""

import json
import subprocess
from pathlib import Path
from typing import Literal

from pydub import AudioSegment

OriginalAudioMode = Literal["replace", "keep_bgm", "mix", "keep_full"]


def get_audio_duration_ms(path: str) -> int:
    audio = AudioSegment.from_file(path)
    return len(audio)


def change_tempo(input_path: str, output_path: str, factor: float) -> None:
    """Change audio tempo without changing pitch using ffmpeg atempo."""
    factor = max(0.5, min(100.0, factor))
    filters = _atempo_filters(factor)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        input_path,
        "-filter:a",
        ",".join(filters),
        output_path,
    ]
    subprocess.run(cmd, check=True)


def create_timeline_audio(
    segments: list[tuple[str, int]],
    output_path: str,
    duration_ms: int,
    volume: float = 1.0,
) -> None:
    """Place segment audio files on a silent timeline."""
    timeline = AudioSegment.silent(duration=max(duration_ms, 1), frame_rate=48000)
    gain_db = _linear_to_db(volume)
    for audio_path, start_ms in segments:
        clip = AudioSegment.from_file(audio_path)
        if volume != 1.0:
            clip += gain_db
        timeline = timeline.overlay(clip, position=max(0, start_ms))
    suffix = Path(output_path).suffix.lower().lstrip(".") or "wav"
    fmt = "mp3" if suffix == "mp3" else "wav"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    timeline.export(output_path, format=fmt)


def mux_dubbed_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    *,
    original_audio_mode: OriginalAudioMode = "replace",
    mix_original_audio: bool = False,
    original_audio_volume: float = 0.25,
    dubbed_audio_volume: float = 1.0,
) -> None:
    """Replace or mix a video's audio track with dubbed audio.

    Modes:
    - replace: chỉ giọng TTS (bỏ hết âm gốc)
    - keep_bgm: tắt thoại gốc (karaoke mid/side), giữ nhạc nền + TTS
    - mix: hạ cả track gốc rồi trộn với TTS
    - keep_full: giữ nguyên âm gốc 100% + chèn TTS lên trên
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    mode: OriginalAudioMode = original_audio_mode
    if mix_original_audio and mode == "replace":
        mode = "mix"

    has_audio = _video_has_audio(video_path)
    if mode in {"keep_bgm", "mix", "keep_full"} and has_audio:
        channels = _audio_channel_count(video_path)
        if mode == "keep_full":
            # Giữ nguyên âm gốc, chỉ overlay TTS
            filter_complex = (
                f"[0:a]volume=1.0[a0];"
                f"[1:a]volume={dubbed_audio_volume}[a1];"
                "[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[a]"
            )
        elif mode == "keep_bgm" and channels >= 2:
            # Zero mid (thoại thường ở giữa), giữ side (nhạc/SFX) rồi trộn TTS
            bg_vol = max(0.05, min(1.5, float(original_audio_volume) or 0.85))
            filter_complex = (
                f"[0:a]stereotools=mlev=0.02:slev=1.15,volume={bg_vol}[bg];"
                f"[1:a]volume={dubbed_audio_volume}[dub];"
                "[bg][dub]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
            )
        elif mode == "keep_bgm":
            # Mono: không tách được thoại/nhạc — hạ gốc rất nhỏ + TTS
            bg_vol = max(0.02, min(0.25, float(original_audio_volume) * 0.3))
            filter_complex = (
                f"[0:a]volume={bg_vol}[bg];"
                f"[1:a]volume={dubbed_audio_volume}[dub];"
                "[bg][dub]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
            )
        else:
            filter_complex = (
                f"[0:a]volume={original_audio_volume}[a0];"
                f"[1:a]volume={dubbed_audio_volume}[a1];"
                "[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[a]"
            )
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            video_path,
            "-i",
            audio_path,
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-strict",
            "-2",
            "-movflags",
            "+faststart",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            video_path,
            "-i",
            audio_path,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-strict",
            "-2",
            "-movflags",
            "+faststart",
            output_path,
        ]
    subprocess.run(cmd, check=True)


def _atempo_filters(factor: float) -> list[str]:
    filters = []
    remaining = factor
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    return filters


def _linear_to_db(volume: float) -> float:
    if volume <= 0:
        return -120.0
    import math

    return 20 * math.log10(volume)


def _video_has_audio(video_path: str) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index",
        "-of",
        "json",
        video_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout or "{}")
    return bool(data.get("streams"))


def _audio_channel_count(video_path: str) -> int:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=channels",
        "-of",
        "json",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        if streams:
            return int(streams[0].get("channels") or 2)
    except Exception:
        pass
    return 2
