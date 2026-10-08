"""Generate and play a short TTS voice sample for UI preview."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from PyQt5.QtCore import QObject, QThread, QUrl, pyqtSignal
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer

from videocaptioner.ui.common.voice_catalog import VoiceOption

_SAMPLE_BY_LANG: dict[str, str] = {
    "vi": "Xin chào, đây là giọng thử của VideoCaptioner. Nghe thử để chọn giọng phù hợp nhé.",
    "zh": "你好，这是配音试听。欢迎选择适合你的声音。",
    "en": "Hello, this is a voice preview from VideoCaptioner.",
    "ja": "こんにちは。これは音声の試聴です。",
    "ko": "안녕하세요. 이것은 음성 미리듣기입니다.",
    "th": "สวัสดี นี่คือตัวอย่างเสียงพากย์",
    "fr": "Bonjour, ceci est un aperçu de la voix.",
    "de": "Hallo, das ist eine Stimmvorschau.",
    "es": "Hola, esta es una vista previa de la voz.",
    "ru": "Здравствуйте, это пробное озвучивание.",
}


def sample_text_for_voice(voice: VoiceOption | str) -> str:
    if isinstance(voice, VoiceOption):
        return _SAMPLE_BY_LANG.get(voice.sample_lang, _SAMPLE_BY_LANG["en"])
    return _SAMPLE_BY_LANG["vi"]


class VoicePreviewThread(QThread):
    """Download a short TTS clip for the selected voice profile."""

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, voice: VoiceOption, parent=None):
        super().__init__(parent)
        self.voice = voice
        self.text = sample_text_for_voice(voice)

    def run(self) -> None:
        try:
            out = (
                Path(tempfile.gettempdir())
                / f"vc_voice_preview_{self.voice.cache_key}.mp3"
            )
            if self.voice.provider == "capcut":
                self._synthesize_capcut(out)
            else:
                asyncio.run(self._synthesize_edge(out))
            if not out.exists() or out.stat().st_size < 100:
                raise RuntimeError("File nghe thử trống hoặc quá ngắn")
            self.finished_ok.emit(str(out))
        except Exception as exc:
            self.failed.emit(str(exc))

    async def _synthesize_edge(self, out: Path) -> None:
        import edge_tts

        communicate = edge_tts.Communicate(
            self.text,
            self.voice.voice_id,
            rate=self.voice.rate,
            pitch=self.voice.pitch,
        )
        await communicate.save(str(out))

    def _synthesize_capcut(self, out: Path) -> None:
        from videocaptioner.core.speech.models import SpeechProviderConfig
        from videocaptioner.core.speech.providers import CapCutSpeechSynthesizer
        from videocaptioner.core.speech.models import SynthesisRequest

        synth = CapCutSpeechSynthesizer(
            SpeechProviderConfig(
                provider="capcut",
                api_key="",
                model="capcut-tts",
                default_voice=self.voice.voice_id,
                edge_rate=self.voice.rate or "1.0",
                capcut_resource_id=self.voice.resource_id,
                timeout=90,
            )
        )
        synth.synthesize(
            SynthesisRequest(
                text=self.text,
                output_path=str(out),
                voice=self.voice.voice_id,
            )
        )


class VoicePreviewPlayer(QObject):
    """Owns the preview worker + media player for a parent widget."""

    status = pyqtSignal(str)
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: VoicePreviewThread | None = None
        self._player = QMediaPlayer(self)
        self._player.stateChanged.connect(self._on_player_state)

    def preview(self, voice: VoiceOption | str) -> None:
        if isinstance(voice, str):
            voice = VoiceOption(label=voice, voice_id=voice)
        if not voice.voice_id:
            self.status.emit("Chưa chọn giọng")
            return
        if self._worker and self._worker.isRunning():
            return

        self._player.stop()
        self.busy_changed.emit(True)
        self.status.emit(f"Đang tạo mẫu: {voice.label}...")
        self._worker = VoicePreviewThread(voice, self)
        self._worker.finished_ok.connect(self._on_ready)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def stop(self) -> None:
        self._player.stop()

    def _on_ready(self, path: str) -> None:
        self.busy_changed.emit(False)
        self.status.emit("Đang phát...")
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self._player.play()

    def _on_failed(self, message: str) -> None:
        self.busy_changed.emit(False)
        self.status.emit(f"Nghe thử lỗi: {message}")

    def _on_player_state(self, state: int) -> None:
        if state == QMediaPlayer.StoppedState:
            if not (self._worker and self._worker.isRunning()):
                if self._player.error() == QMediaPlayer.NoError:
                    self.status.emit("Hết đoạn nghe thử.")
