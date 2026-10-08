"""翻译器类型枚举"""

from enum import Enum


class TranslatorType(Enum):
    """翻译器类型"""

    OPENAI = "openai"
    GOOGLE = "google"
    BING = "bing"
    DEEPLX = "deeplx"
    CHATGPT_WEB = "chatgpt-web"


class TargetLanguage(Enum):
    """目标语言枚举"""

    # 中文
    SIMPLIFIED_CHINESE = "Tiếng Trung (Giản thể)"
    TRADITIONAL_CHINESE = "Tiếng Trung (Phồn thể)"

    # 英语
    ENGLISH = "Tiếng Anh"
    ENGLISH_US = "Tiếng Anh (Mỹ)"
    ENGLISH_UK = "Tiếng Anh (Anh)"

    # 亚洲语言
    JAPANESE = "Tiếng Nhật"
    KOREAN = "Tiếng Hàn"
    CANTONESE = "Quảng Đông"
    THAI = "Tiếng Thái"
    VIETNAMESE = "Tiếng Việt"
    INDONESIAN = "Tiếng Indonesia"
    MALAY = "Tiếng Malay"
    TAGALOG = "Tiếng Philippines"

    # 欧洲语言
    FRENCH = "Tiếng Pháp"
    GERMAN = "Tiếng Đức"
    SPANISH = "Tiếng Tây Ban Nha"
    SPANISH_LATAM = "Tiếng Tây Ban Nha (Latin)"
    RUSSIAN = "Tiếng Nga"
    PORTUGUESE = "Tiếng Bồ Đào Nha"
    PORTUGUESE_BR = "Tiếng Bồ Đào Nha (Brazil)"
    PORTUGUESE_PT = "Tiếng Bồ Đào Nha (Bồ Đào Nha)"
    ITALIAN = "Tiếng Ý"
    DUTCH = "Tiếng Hà Lan"
    POLISH = "Tiếng Ba Lan"
    TURKISH = "Tiếng Thổ Nhĩ Kỳ"
    GREEK = "Tiếng Hy Lạp"
    CZECH = "Tiếng Séc"
    SWEDISH = "Tiếng Thụy Điển"
    DANISH = "Tiếng Đan Mạch"
    FINNISH = "Tiếng Phần Lan"
    NORWEGIAN = "Tiếng Na Uy"
    HUNGARIAN = "Tiếng Hungary"
    ROMANIAN = "Tiếng Romania"
    BULGARIAN = "Tiếng Bulgaria"
    UKRAINIAN = "Tiếng Ukraine"

    # 中东语言
    ARABIC = "Tiếng Ả Rập"
    HEBREW = "Tiếng Hebrew"
    PERSIAN = "Tiếng Ba Tư"

    @classmethod
    def _missing_(cls, value):
        """Map legacy Chinese labels from settings.json → member."""
        legacy = {
            "简体中文": cls.SIMPLIFIED_CHINESE,
            "繁体中文": cls.TRADITIONAL_CHINESE,
            "繁體中文": cls.TRADITIONAL_CHINESE,
            "英语": cls.ENGLISH,
            "英语(美国)": cls.ENGLISH_US,
            "英语(英国)": cls.ENGLISH_UK,
            "日本語": cls.JAPANESE,
            "韩语": cls.KOREAN,
            "粤语": cls.CANTONESE,
            "泰语": cls.THAI,
            "越南语": cls.VIETNAMESE,
            "印尼语": cls.INDONESIAN,
            "马来语": cls.MALAY,
            "菲律宾语": cls.TAGALOG,
            "法语": cls.FRENCH,
            "德语": cls.GERMAN,
            "西班牙语": cls.SPANISH,
            "西班牙语(拉丁美洲)": cls.SPANISH_LATAM,
            "俄语": cls.RUSSIAN,
            "葡萄牙语": cls.PORTUGUESE,
            "葡萄牙语(巴西)": cls.PORTUGUESE_BR,
            "葡萄牙语(葡萄牙)": cls.PORTUGUESE_PT,
            "意大利语": cls.ITALIAN,
            "荷兰语": cls.DUTCH,
            "波兰语": cls.POLISH,
            "土耳其语": cls.TURKISH,
            "希腊语": cls.GREEK,
            "捷克语": cls.CZECH,
            "瑞典语": cls.SWEDISH,
            "丹麦语": cls.DANISH,
            "芬兰语": cls.FINNISH,
            "挪威语": cls.NORWEGIAN,
            "匈牙利语": cls.HUNGARIAN,
            "罗马尼亚语": cls.ROMANIAN,
            "保加利亚语": cls.BULGARIAN,
            "乌克兰语": cls.UKRAINIAN,
            "阿拉伯语": cls.ARABIC,
            "希伯来语": cls.HEBREW,
            "波斯语": cls.PERSIAN,
        }
        return legacy.get(value)


# Google Translate 语言代码映射
GOOGLE_LANG_MAP = {
    # 中文
    TargetLanguage.SIMPLIFIED_CHINESE: "zh-CN",
    TargetLanguage.TRADITIONAL_CHINESE: "zh-TW",
    # 英语
    TargetLanguage.ENGLISH: "en",
    TargetLanguage.ENGLISH_US: "en",
    TargetLanguage.ENGLISH_UK: "en",
    # 亚洲语言
    TargetLanguage.JAPANESE: "ja",
    TargetLanguage.KOREAN: "ko",
    TargetLanguage.CANTONESE: "yue",
    TargetLanguage.THAI: "th",
    TargetLanguage.VIETNAMESE: "vi",
    TargetLanguage.INDONESIAN: "id",
    TargetLanguage.MALAY: "ms",
    TargetLanguage.TAGALOG: "tl",
    # 欧洲语言
    TargetLanguage.FRENCH: "fr",
    TargetLanguage.GERMAN: "de",
    TargetLanguage.SPANISH: "es",
    TargetLanguage.SPANISH_LATAM: "es",
    TargetLanguage.RUSSIAN: "ru",
    TargetLanguage.PORTUGUESE: "pt",
    TargetLanguage.PORTUGUESE_BR: "pt",
    TargetLanguage.PORTUGUESE_PT: "pt",
    TargetLanguage.ITALIAN: "it",
    TargetLanguage.DUTCH: "nl",
    TargetLanguage.POLISH: "pl",
    TargetLanguage.TURKISH: "tr",
    TargetLanguage.GREEK: "el",
    TargetLanguage.CZECH: "cs",
    TargetLanguage.SWEDISH: "sv",
    TargetLanguage.DANISH: "da",
    TargetLanguage.FINNISH: "fi",
    TargetLanguage.NORWEGIAN: "no",
    TargetLanguage.HUNGARIAN: "hu",
    TargetLanguage.ROMANIAN: "ro",
    TargetLanguage.BULGARIAN: "bg",
    TargetLanguage.UKRAINIAN: "uk",
    # 中东语言
    TargetLanguage.ARABIC: "ar",
    TargetLanguage.HEBREW: "he",
    TargetLanguage.PERSIAN: "fa",
}

# Bing Translator 语言代码映射
BING_LANG_MAP = {
    # 中文
    TargetLanguage.SIMPLIFIED_CHINESE: "zh-Hans",
    TargetLanguage.TRADITIONAL_CHINESE: "zh-Hant",
    # 英语
    TargetLanguage.ENGLISH: "en",
    TargetLanguage.ENGLISH_US: "en",
    TargetLanguage.ENGLISH_UK: "en",
    # 亚洲语言
    TargetLanguage.JAPANESE: "ja",
    TargetLanguage.KOREAN: "ko",
    TargetLanguage.CANTONESE: "yue",
    TargetLanguage.THAI: "th",
    TargetLanguage.VIETNAMESE: "vi",
    TargetLanguage.INDONESIAN: "id",
    TargetLanguage.MALAY: "ms",
    TargetLanguage.TAGALOG: "fil",
    # 欧洲语言
    TargetLanguage.FRENCH: "fr",
    TargetLanguage.GERMAN: "de",
    TargetLanguage.SPANISH: "es",
    TargetLanguage.SPANISH_LATAM: "es",
    TargetLanguage.RUSSIAN: "ru",
    TargetLanguage.PORTUGUESE: "pt",
    TargetLanguage.PORTUGUESE_BR: "pt",
    TargetLanguage.PORTUGUESE_PT: "pt-PT",
    TargetLanguage.ITALIAN: "it",
    TargetLanguage.DUTCH: "nl",
    TargetLanguage.POLISH: "pl",
    TargetLanguage.TURKISH: "tr",
    TargetLanguage.GREEK: "el",
    TargetLanguage.CZECH: "cs",
    TargetLanguage.SWEDISH: "sv",
    TargetLanguage.DANISH: "da",
    TargetLanguage.FINNISH: "fi",
    TargetLanguage.NORWEGIAN: "nb",
    TargetLanguage.HUNGARIAN: "hu",
    TargetLanguage.ROMANIAN: "ro",
    TargetLanguage.BULGARIAN: "bg",
    TargetLanguage.UKRAINIAN: "uk",
    # 中东语言
    TargetLanguage.ARABIC: "ar",
    TargetLanguage.HEBREW: "he",
    TargetLanguage.PERSIAN: "fa",
}

# DeepL 语言代码映射
DEEPL_LANG_MAP = {
    # 中文
    TargetLanguage.SIMPLIFIED_CHINESE: "zh-Hans",
    TargetLanguage.TRADITIONAL_CHINESE: "zh-Hant",
    # 英语
    TargetLanguage.ENGLISH: "en",
    TargetLanguage.ENGLISH_US: "en-US",
    TargetLanguage.ENGLISH_UK: "en-GB",
    # 亚洲语言
    TargetLanguage.JAPANESE: "ja",
    TargetLanguage.KOREAN: "ko",
    TargetLanguage.INDONESIAN: "id",
    # 欧洲语言
    TargetLanguage.FRENCH: "fr",
    TargetLanguage.GERMAN: "de",
    TargetLanguage.SPANISH: "es",
    TargetLanguage.RUSSIAN: "ru",
    TargetLanguage.PORTUGUESE: "pt",
    TargetLanguage.PORTUGUESE_BR: "pt-BR",
    TargetLanguage.PORTUGUESE_PT: "pt-PT",
    TargetLanguage.ITALIAN: "it",
    TargetLanguage.DUTCH: "nl",
    TargetLanguage.POLISH: "pl",
    TargetLanguage.TURKISH: "tr",
    TargetLanguage.GREEK: "el",
    TargetLanguage.CZECH: "cs",
    TargetLanguage.SWEDISH: "sv",
    TargetLanguage.DANISH: "da",
    TargetLanguage.FINNISH: "fi",
    TargetLanguage.NORWEGIAN: "nb",
    TargetLanguage.HUNGARIAN: "hu",
    TargetLanguage.ROMANIAN: "ro",
    TargetLanguage.BULGARIAN: "bg",
    TargetLanguage.UKRAINIAN: "uk",
    # 中东语言
    TargetLanguage.ARABIC: "ar",
}


def get_language_code(target_language: TargetLanguage, translator_type: str) -> str:
    """
    获取翻译服务对应的语言代码

    Args:
        target_language: 目标语言枚举
        translator_type: 翻译器类型（google/bing/deeplx）

    Returns:
        语言代码字符串
    """
    lang_map = {
        "google": GOOGLE_LANG_MAP,
        "bing": BING_LANG_MAP,
        "deeplx": DEEPL_LANG_MAP,
    }

    # 获取对应的语言映射
    mapping = lang_map.get(translator_type, {})

    # 使用枚举成员查找语言代码（与 .value 无关）
    if target_language in mapping:
        return mapping[target_language]

    # 默认返回简体中文
    return mapping.get(TargetLanguage.SIMPLIFIED_CHINESE, "zh-CN")
