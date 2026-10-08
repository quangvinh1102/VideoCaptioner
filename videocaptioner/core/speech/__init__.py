"""Speech synthesis provider layer for dubbing."""

from .models import SpeechProviderConfig, SynthesisRequest, SynthesisResult
from .providers import (
    CapCutSpeechSynthesizer,
    EdgeTTSSpeechSynthesizer,
    GeminiSpeechSynthesizer,
    SiliconFlowSpeechSynthesizer,
    SpeechSynthesizer,
    create_speech_synthesizer,
)

__all__ = [
    "CapCutSpeechSynthesizer",
    "GeminiSpeechSynthesizer",
    "EdgeTTSSpeechSynthesizer",
    "SiliconFlowSpeechSynthesizer",
    "SpeechProviderConfig",
    "SpeechSynthesizer",
    "SynthesisRequest",
    "SynthesisResult",
    "create_speech_synthesizer",
]
