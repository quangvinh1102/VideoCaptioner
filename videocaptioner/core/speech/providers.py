"""Speech synthesis provider implementations."""

import asyncio
import base64
import hashlib
import threading
import time
import wave
from pathlib import Path
from typing import Any, Protocol

import edge_tts
import requests

from videocaptioner.core.utils.cache import get_tts_cache
from videocaptioner.core.utils.logger import setup_logger

from .models import SpeechProviderConfig, SynthesisRequest, SynthesisResult

logger = setup_logger("speech")


class SpeechSynthesizer(Protocol):
    """Provider-neutral synthesis interface used by the dubbing pipeline."""

    config: SpeechProviderConfig

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """Synthesize one utterance to ``request.output_path``."""
        ...


def create_speech_synthesizer(config: SpeechProviderConfig) -> SpeechSynthesizer:
    if config.provider == "siliconflow":
        return SiliconFlowSpeechSynthesizer(config)
    if config.provider == "gemini":
        return GeminiSpeechSynthesizer(config)
    if config.provider == "edge":
        return EdgeTTSSpeechSynthesizer(config)
    if config.provider == "capcut":
        return CapCutSpeechSynthesizer(config)
    raise ValueError(f"Unsupported speech provider: {config.provider}")


class CapCutSpeechSynthesizer:
    """CapCut / Jianying cloud TTS (popular reup voices like Nhỏ Ngọt Ngào)."""

    _lock = threading.Lock()

    def __init__(self, config: SpeechProviderConfig):
        self.config = config

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        if request.clone_audio_path or request.clone_audio_text:
            raise ValueError("CapCut TTS does not support voice cloning here")
        voice = request.voice or self.config.default_voice
        if not voice:
            raise ValueError("CapCut voice_type is required")
        text = (request.text or "").strip()
        if not text:
            raise ValueError("CapCut TTS text is empty")
        text = " ".join(text.replace("\u0000", " ").split())
        if len(text) > 900:
            text = text[:900]

        path = Path(request.output_path).with_suffix(".mp3")
        path.parent.mkdir(parents=True, exist_ok=True)

        rate = self._capcut_rate()
        resource_id = self.config.capcut_resource_id or None
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                with self._lock:
                    self._synthesize_once(text, voice, resource_id, rate, path)
                if path.exists() and path.stat().st_size > 0:
                    return SynthesisResult(
                        output_path=str(path),
                        voice=voice,
                        format="mp3",
                        provider_metadata={
                            "provider": "capcut",
                            "resource_id": resource_id or "",
                            "rate": rate,
                            "attempts": attempt,
                        },
                    )
                last_error = ValueError("CapCut TTS returned empty audio")
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "CapCut TTS attempt %s failed (%s): %s", attempt, voice, exc
                )
                path.unlink(missing_ok=True)
                time.sleep(0.8 * attempt)
        raise RuntimeError(f"CapCut TTS failed after retries: {last_error}")

    def _capcut_rate(self) -> str:
        # Prefer explicit CapCut rate string like "1.0"; else map from speed float.
        if self.config.edge_rate and not self.config.edge_rate.endswith("%"):
            return self.config.edge_rate
        if self.config.edge_rate.endswith("%"):
            try:
                pct = float(self.config.edge_rate.replace("%", "").replace("+", ""))
                return f"{1.0 + pct / 100.0:.2f}"
            except ValueError:
                pass
        return f"{float(self.config.speed):.2f}"

    def _synthesize_once(
        self,
        text: str,
        voice: str,
        resource_id: str | None,
        rate: str,
        path: Path,
    ) -> None:
        from capcut_tts_api import CapCutClient

        from videocaptioner.config import RESOURCE_PATH

        catalog = RESOURCE_PATH / "capcut_voices_vi.json"
        client = CapCutClient()
        kwargs = {"texts": text, "voice": voice, "rate": rate}
        if resource_id:
            kwargs["resource_id"] = resource_id
        elif catalog.exists():
            kwargs["resource_id"] = self._lookup_resource_id(catalog, voice)

        create_res = client.create_tts_task(**kwargs)
        tasks = (create_res.get("data") or {}).get("tasks") or []
        if not tasks:
            raise RuntimeError(f"CapCut không trả task: {create_res}")
        task_id = tasks[0]["id"]
        token = tasks[0]["token"]

        deadline = time.time() + max(self.config.timeout, 60)
        payload = None
        while time.time() < deadline:
            query_res = client.query_tts_task(task_id, token)
            qtasks = (query_res.get("data") or {}).get("tasks") or []
            if not qtasks:
                time.sleep(1.2)
                continue
            status = (qtasks[0].get("status") or "").lower()
            if status in {"succeed", "success"}:
                payload = qtasks[0].get("payload")
                break
            if status in {"failed", "fail"}:
                raise RuntimeError(f"CapCut TTS failed: {query_res}")
            time.sleep(1.2)
        else:
            raise TimeoutError("CapCut TTS timed out")

        if isinstance(payload, str):
            import json

            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise RuntimeError("CapCut payload không hợp lệ")
        items = payload.get("audio_subtitles") or []
        if not items:
            raise RuntimeError("CapCut không có audio_subtitles")
        url = items[0].get("speech_url")
        if not url:
            raise RuntimeError("CapCut thiếu speech_url")

        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        path.write_bytes(resp.content)

    @staticmethod
    def _lookup_resource_id(catalog: Path, voice_type: str) -> str | None:
        import json

        try:
            data = json.loads(catalog.read_text(encoding="utf-8"))
        except Exception:
            return None
        for item in data:
            if item.get("voice_type") == voice_type:
                return item.get("resource_id")
        return None


class EdgeTTSSpeechSynthesizer:
    """Microsoft Edge online TTS synthesizer.

    This provider uses the unofficial Edge read-aloud endpoint through edge-tts.
    It does not require an API key and does not support voice cloning.
    """

    DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
    _lock = threading.Lock()

    def __init__(self, config: SpeechProviderConfig):
        self.config = config

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        if request.clone_audio_path or request.clone_audio_text:
            raise ValueError("Edge TTS does not support voice cloning")
        voice = request.voice or self.config.default_voice or self.DEFAULT_VOICE
        text = (request.text or "").strip()
        if not text:
            raise ValueError("Edge TTS text is empty")
        # Edge rejects some control chars / overlong lines
        text = " ".join(text.replace("\u0000", " ").split())
        if len(text) > 900:
            text = text[:900]

        path = Path(request.output_path).with_suffix(".mp3")
        path.parent.mkdir(parents=True, exist_ok=True)

        last_error: Exception | None = None
        for attempt in range(1, 5):
            try:
                # Serialize Edge calls — concurrent asyncio.run + Edge CDN often yields NoAudioReceived
                with self._lock:
                    asyncio.run(self._save(text, voice, path))
                if path.exists() and path.stat().st_size > 0:
                    return SynthesisResult(
                        output_path=str(path),
                        voice=voice,
                        format="mp3",
                        provider_metadata={
                            "rate": self._edge_rate(),
                            "volume": self._edge_volume(),
                            "pitch": self._edge_pitch(),
                            "attempts": attempt,
                        },
                    )
                last_error = ValueError("Edge TTS returned an empty audio file")
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Edge TTS attempt %s failed (%s): %s",
                    attempt,
                    voice,
                    exc,
                )
                path.unlink(missing_ok=True)
                time.sleep(0.8 * attempt)

        raise RuntimeError(f"Edge TTS failed after retries: {last_error}")

    async def _save(self, text: str, voice: str, path: Path) -> None:
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=self._edge_rate(),
            volume=self._edge_volume(),
            pitch=self._edge_pitch(),
            connect_timeout=min(self.config.timeout, 30),
            receive_timeout=self.config.timeout,
        )
        await communicate.save(str(path))

    def _edge_rate(self) -> str:
        if self.config.edge_rate:
            return self.config.edge_rate
        percent = round((self.config.speed - 1.0) * 100)
        percent = max(-50, min(100, percent))
        return f"{percent:+d}%"

    def _edge_pitch(self) -> str:
        pitch = (self.config.edge_pitch or "+0Hz").strip()
        if not pitch:
            return "+0Hz"
        # Accept bare numbers like "+2" / "-3"
        if pitch[-2:].lower() != "hz":
            pitch = f"{pitch}Hz" if pitch[0] in "+-" else f"+{pitch}Hz"
        return pitch

    def _edge_volume(self) -> str:
        percent = round(self.config.gain)
        percent = max(-50, min(50, percent))
        return f"{percent:+d}%"


class SiliconFlowSpeechSynthesizer:
    """SiliconFlow CosyVoice2-compatible synthesizer."""

    DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"

    def __init__(self, config: SpeechProviderConfig):
        if not config.api_key:
            raise ValueError("SiliconFlow API key is required")
        self.config = config
        self.base_url = (config.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.cache = get_tts_cache()

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        voice = self._resolve_voice(request)
        payload: dict[str, Any] = {
            "model": self.config.model,
            "input": self._build_input(request),
            "voice": voice,
            "response_format": self.config.response_format,
            "sample_rate": self.config.sample_rate,
            "speed": self.config.speed,
            "gain": self.config.gain,
            "stream": False,
        }
        response = self._post_speech(payload)
        path = Path(request.output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return SynthesisResult(
            output_path=str(path),
            voice=voice,
            format=self.config.response_format,
            provider_metadata={"content_type": response.headers.get("content-type", "")},
        )

    def _post_speech(self, payload: dict[str, Any]) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = requests.post(
                    f"{self.base_url}/audio/speech",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.config.timeout,
                )
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if not response.content:
                    raise ValueError("SiliconFlow TTS returned an empty audio body")
                if "json" in content_type.lower():
                    raise ValueError(f"SiliconFlow TTS returned JSON instead of audio: {response.text[:300]}")
                return response
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"SiliconFlow TTS failed after retries: {last_error}")

    def _resolve_voice(self, request: SynthesisRequest) -> str:
        if request.clone_audio_path and request.clone_audio_text:
            return self._upload_voice(request.clone_audio_path, request.clone_audio_text)
        voice = request.voice or self.config.default_voice
        if not voice:
            voice = f"{self.config.model}:alex"
        return voice

    def _build_input(self, request: SynthesisRequest) -> str:
        prompt = request.style_prompt or self.config.style_prompt
        if prompt:
            return f"{prompt.strip()}<|endofprompt|>{request.text.strip()}"
        return request.text

    def _upload_voice(self, audio_path: str, transcript: str) -> str:
        audio_file = Path(audio_path)
        if not audio_file.exists():
            raise FileNotFoundError(f"Voice clone reference audio not found: {audio_path}")
        cache_key = self._voice_cache_key(audio_file, transcript)
        cached = self.cache.get(cache_key)
        if cached:
            return str(cached)

        custom_name = f"videocaptioner_{hashlib.md5(cache_key.encode()).hexdigest()[:12]}"
        with audio_file.open("rb") as f:
            response = requests.post(
                f"{self.base_url}/uploads/audio/voice",
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                files={"file": (audio_file.name, f, _guess_mime(audio_file))},
                data={
                    "model": self.config.model,
                    "customName": custom_name,
                    "text": transcript,
                },
                timeout=self.config.timeout,
            )
        response.raise_for_status()
        uri = response.json().get("uri")
        if not uri:
            raise ValueError(f"SiliconFlow upload did not return a voice uri: {response.text}")
        self.cache.set(cache_key, uri, expire=86400 * 2)
        return str(uri)

    def _voice_cache_key(self, audio_file: Path, transcript: str) -> str:
        digest = hashlib.md5(audio_file.read_bytes()).hexdigest()
        raw = f"speech_voice:{self.config.model}:{digest}:{transcript}"
        return hashlib.md5(raw.encode()).hexdigest()


class GeminiSpeechSynthesizer:
    """Gemini native speech generation synthesizer."""

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    SAMPLE_RATE = 24000

    def __init__(self, config: SpeechProviderConfig):
        if not config.api_key:
            raise ValueError("Gemini API key is required")
        self.config = config

    def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        voice = request.voice or self.config.default_voice or "Kore"
        prompt = self._build_prompt(request)
        response = requests.post(
            self._model_url(),
            headers={
                "x-goog-api-key": self.config.api_key,
                "Content-Type": "application/json",
            },
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {
                                "voiceName": voice,
                            }
                        }
                    },
                },
            },
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        pcm = self._extract_pcm(response.json())
        path = Path(request.output_path).with_suffix(".wav")
        self._write_wav(pcm, path)
        return SynthesisResult(
            output_path=str(path),
            voice=voice,
            format="wav",
            provider_metadata={"sample_rate": self.SAMPLE_RATE},
        )

    def _model_url(self) -> str:
        base_url = (self.config.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        if base_url.endswith("/v1beta"):
            return f"{base_url}/models/{self.config.model}:generateContent"
        return f"{base_url}/v1beta/models/{self.config.model}:generateContent"

    def _build_prompt(self, request: SynthesisRequest) -> str:
        prompt = request.style_prompt or self.config.style_prompt
        if prompt:
            return f"{prompt.strip()}\n\nTranscript:\n{request.text.strip()}"
        return f"Read this subtitle line naturally and clearly.\n\nTranscript:\n{request.text.strip()}"

    @staticmethod
    def _extract_pcm(data: dict[str, Any]) -> bytes:
        try:
            for part in data["candidates"][0]["content"]["parts"]:
                inline_data = part.get("inlineData") or part.get("inline_data")
                if inline_data and inline_data.get("data"):
                    return base64.b64decode(inline_data["data"])
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"Invalid Gemini TTS response: {data}") from exc
        raise ValueError(f"Gemini TTS response did not include audio: {data}")

    @classmethod
    def _write_wav(cls, pcm: bytes, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(cls.SAMPLE_RATE)
            wf.writeframes(pcm)


def _guess_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".opus":
        return "audio/opus"
    if suffix == ".pcm":
        return "audio/pcm"
    return "audio/mpeg"
