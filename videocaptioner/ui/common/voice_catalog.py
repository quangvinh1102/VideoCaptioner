"""Voice catalog for quick dub UI (CapCut + Edge TTS).

CapCut cloud voices (Nhỏ Ngọt Ngào, Giọng Nữ Phổ Thông…) are the ones
creators usually pick inside CapCut. Edge voices remain as free fallbacks
with rate/pitch style variants.
"""

from __future__ import annotations

from dataclasses import dataclass

from videocaptioner.core.translate.types import TargetLanguage


@dataclass(frozen=True)
class VoiceOption:
    """One selectable TTS voice profile."""

    label: str
    voice_id: str
    rate: str = "+0%"
    pitch: str = "+0Hz"
    sample_lang: str = "vi"
    provider: str = "edge"  # edge | capcut
    resource_id: str = ""

    @property
    def cache_key(self) -> str:
        safe = (
            f"{self.provider}_{self.voice_id}_{self.resource_id}_{self.rate}_{self.pitch}"
            .replace("%", "p")
            .replace("+", "plus")
            .replace("-", "m")
            .replace(":", "_")
            .replace("/", "_")
        )
        return safe


def _capcut(
    label: str,
    voice_type: str,
    resource_id: str,
    *,
    rate: str = "1.0",
) -> VoiceOption:
    return VoiceOption(
        label=label,
        voice_id=voice_type,
        rate=rate,
        pitch="+0Hz",
        sample_lang="vi",
        provider="capcut",
        resource_id=resource_id,
    )


# Display order: CapCut VI first (reup favorites), then Edge VI styles, then others.
VOICES: list[VoiceOption] = [
    # —— CapCut Việt (giọng hay dùng trong CapCut) ——
    _capcut(
        "🎬 CapCut — Nhỏ Ngọt Ngào ★",
        "BV421_vivn_streaming",
        "7252594014782755330",
    ),
    _capcut(
        "🎬 CapCut — Giọng Nữ Phổ Thông",
        "vi_female_huong",
        "7264854897953083905",
    ),
    _capcut(
        "🎬 CapCut — Cô Gái Hoạt Ngôn",
        "BV074_streaming",
        "7102355709945188865",
    ),
    _capcut(
        "🎬 CapCut — Giọng Bé",
        "BV074_streaming_dsp",
        "7550087831092251920",
    ),
    _capcut(
        "🎬 CapCut — Mai",
        "BV562_streaming",
        "7483736254694035984",
    ),
    _capcut(
        "🎬 CapCut — Ban Mai",
        "multi_female_yangguangnv_uranus_bigtts",
        "7637456432522218773",
    ),
    _capcut(
        "🎬 CapCut — Review Phim",
        "multi_female_richgirl_uranus_bigtts",
        "7637460351541447956",
    ),
    _capcut(
        "🎬 CapCut — Bản Tin nữ",
        "multi_female_sisi_uranus_bigtts",
        "7637455857285860629",
    ),
    _capcut(
        "🎬 CapCut — Giọng Gái Mới Lớn",
        "multi_female_peiqi_uranus_bigtts",
        "7637458789033151751",
    ),
    _capcut(
        "🎬 CapCut — Việt Méo",
        "BV075_streaming_vibrato_dsp",
        "7569450639810465040",
    ),
    _capcut(
        "🎬 CapCut — Hoài My (trong CapCut)",
        "vi-VN-HoaiMyNeural",
        "7371666434650280464",
    ),
    _capcut(
        "🎬 CapCut — Nam Minh (trong CapCut)",
        "vi-VN-NamMinhNeural",
        "7371666524727153168",
    ),
    _capcut(
        "🎬 CapCut — Thanh Niên Tự Tin",
        "BV075_streaming",
        "7102355803792740865",
    ),
    # —— Edge · Tiếng Việt · Nữ ——
    VoiceOption("🇻🇳 Edge — Hoài My (chuẩn)", "vi-VN-HoaiMyNeural"),
    VoiceOption(
        "🇻🇳 Edge — Hoài My ngọt ngào",
        "vi-VN-HoaiMyNeural",
        rate="-5%",
        pitch="+4Hz",
    ),
    VoiceOption(
        "🇻🇳 Edge — Hoài My dịu êm",
        "vi-VN-HoaiMyNeural",
        rate="-10%",
        pitch="+2Hz",
    ),
    VoiceOption(
        "🇻🇳 Edge — Hoài My kể chuyện",
        "vi-VN-HoaiMyNeural",
        rate="-14%",
        pitch="-1Hz",
    ),
    VoiceOption(
        "🇻🇳 Edge — Hoài My trẻ trung",
        "vi-VN-HoaiMyNeural",
        rate="+8%",
        pitch="+5Hz",
    ),
    VoiceOption(
        "🇻🇳 Edge — Hoài My nhanh rõ",
        "vi-VN-HoaiMyNeural",
        rate="+15%",
        pitch="+2Hz",
    ),
    VoiceOption(
        "🇻🇳 Edge — Ava đa ngôn ngữ",
        "en-US-AvaMultilingualNeural",
        rate="-2%",
        pitch="+1Hz",
        sample_lang="vi",
    ),
    VoiceOption(
        "🇻🇳 Edge — Emma đa ngôn ngữ",
        "en-US-EmmaMultilingualNeural",
        rate="-4%",
        pitch="+2Hz",
        sample_lang="vi",
    ),
    # —— Edge · Tiếng Việt · Nam ——
    VoiceOption("🇻🇳 Edge — Nam Minh (chuẩn)", "vi-VN-NamMinhNeural"),
    VoiceOption(
        "🇻🇳 Edge — Nam Minh trầm",
        "vi-VN-NamMinhNeural",
        rate="-5%",
        pitch="-4Hz",
    ),
    # —— Trung ——
    VoiceOption("🇨🇳 Nữ — Xiaoxiao", "zh-CN-XiaoxiaoNeural", sample_lang="zh"),
    VoiceOption("🇨🇳 Nữ — Xiaoyi", "zh-CN-XiaoyiNeural", sample_lang="zh"),
    VoiceOption("🇨🇳 Nam — Yunxi", "zh-CN-YunxiNeural", sample_lang="zh"),
    # —— Anh ——
    VoiceOption("🇺🇸 Nữ — Jenny", "en-US-JennyNeural", sample_lang="en"),
    VoiceOption("🇺🇸 Nữ — Aria", "en-US-AriaNeural", sample_lang="en"),
    VoiceOption("🇺🇸 Nam — Guy", "en-US-GuyNeural", sample_lang="en"),
    # —— Khác ——
    VoiceOption("🇯🇵 Nữ — Nanami", "ja-JP-NanamiNeural", sample_lang="ja"),
    VoiceOption("🇰🇷 Nữ — SunHi", "ko-KR-SunHiNeural", sample_lang="ko"),
    VoiceOption("🇹🇭 Nữ — Premwadee", "th-TH-PremwadeeNeural", sample_lang="th"),
]

_DEFAULT_VOICE_BY_LANG: dict[TargetLanguage, str] = {
    TargetLanguage.VIETNAMESE: "BV421_vivn_streaming",  # CapCut Nhỏ Ngọt Ngào
    TargetLanguage.ENGLISH: "en-US-JennyNeural",
    TargetLanguage.SIMPLIFIED_CHINESE: "zh-CN-XiaoxiaoNeural",
    TargetLanguage.TRADITIONAL_CHINESE: "zh-CN-XiaoxiaoNeural",
    TargetLanguage.JAPANESE: "ja-JP-NanamiNeural",
    TargetLanguage.KOREAN: "ko-KR-SunHiNeural",
    TargetLanguage.THAI: "th-TH-PremwadeeNeural",
    TargetLanguage.FRENCH: "fr-FR-DeniseNeural",
    TargetLanguage.GERMAN: "de-DE-KatjaNeural",
    TargetLanguage.SPANISH: "es-ES-ElviraNeural",
    TargetLanguage.RUSSIAN: "ru-RU-SvetlanaNeural",
}


def default_voice_index_for_lang(lang: TargetLanguage) -> int:
    preferred = _DEFAULT_VOICE_BY_LANG.get(lang)
    if not preferred:
        return 0
    for i, v in enumerate(VOICES):
        if v.voice_id == preferred:
            return i
    return 0
