"""Vietnamese display labels for enum/option values (storage values stay Chinese)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, List

# Chinese (or mixed) storage/display value → Vietnamese UI label
VI_LABELS: dict[str, str] = {
    # TargetLanguage / TranscribeLanguage
    "简体中文": "Tiếng Trung (Giản thể)",
    "繁体中文": "Tiếng Trung (Phồn thể)",
    "繁體中文": "Tiếng Trung (Phồn thể)",
    "英语": "Tiếng Anh",
    "英语(美国)": "Tiếng Anh (Mỹ)",
    "英语(英国)": "Tiếng Anh (Anh)",
    "中文": "Tiếng Trung",
    "韩语": "Tiếng Hàn",
    "粤语": "Quảng Đông",
    "泰语": "Tiếng Thái",
    "越南语": "Tiếng Việt",
    "印尼语": "Tiếng Indonesia",
    "马来语": "Tiếng Malay",
    "菲律宾语": "Tiếng Philippines",
    "法语": "Tiếng Pháp",
    "德语": "Tiếng Đức",
    "西班牙语": "Tiếng Tây Ban Nha",
    "西班牙语(拉丁美洲)": "Tiếng Tây Ban Nha (Latin)",
    "俄语": "Tiếng Nga",
    "葡萄牙语": "Tiếng Bồ Đào Nha",
    "葡萄牙语(巴西)": "Tiếng Bồ Đào Nha (Brazil)",
    "葡萄牙语(葡萄牙)": "Tiếng Bồ Đào Nha (Bồ Đào Nha)",
    "意大利语": "Tiếng Ý",
    "荷兰语": "Tiếng Hà Lan",
    "波兰语": "Tiếng Ba Lan",
    "土耳其语": "Tiếng Thổ Nhĩ Kỳ",
    "希腊语": "Tiếng Hy Lạp",
    "捷克语": "Tiếng Séc",
    "瑞典语": "Tiếng Thụy Điển",
    "丹麦语": "Tiếng Đan Mạch",
    "芬兰语": "Tiếng Phần Lan",
    "挪威语": "Tiếng Na Uy",
    "匈牙利语": "Tiếng Hungary",
    "罗马尼亚语": "Tiếng Romania",
    "保加利亚语": "Tiếng Bulgaria",
    "乌克兰语": "Tiếng Ukraine",
    "阿拉伯语": "Tiếng Ả Rập",
    "希伯来语": "Tiếng Hebrew",
    "波斯语": "Tiếng Ba Tư",
    "自动检测": "Tự động phát hiện",
    "日本語": "Tiếng Nhật",
    # Translator / LLM
    "LLM 大模型翻译": "Dịch bằng LLM",
    "DeepLx 翻译": "Dịch DeepLx",
    "微软翻译": "Dịch Microsoft (Bing)",
    "谷歌翻译": "Dịch Google",
    "OpenAI 兼容": "Tương thích OpenAI",
    # ASR models
    "B 接口": "Bilibili ASR (miễn phí)",
    "J 接口": "Jianying ASR (miễn phí)",
    "Whisper [API] ✨": "Whisper [API] ✨",
    "FasterWhisper ✨": "FasterWhisper ✨",
    "WhisperCpp": "WhisperCpp",
    # Subtitle layout / render
    "译文在上": "Bản dịch phía trên",
    "原文在上": "Bản gốc phía trên",
    "仅原文": "Chỉ bản gốc",
    "仅译文": "Chỉ bản dịch",
    "ASS 样式": "Kiểu ASS",
    "圆角背景": "Nền bo góc",
    # Video quality
    "极高质量": "Chất lượng cực cao",
    "高质量": "Chất lượng cao",
    "中等质量": "Chất lượng trung bình",
    "低质量": "Chất lượng thấp",
    # Batch
    "批量转录": "Nhận diện hàng loạt",
    "批量字幕": "Phụ đề hàng loạt",
    "转录+字幕": "Nhận diện + phụ đề",
    "全流程处理": "Xử lý toàn bộ",
    "等待中": "Đang chờ",
    "处理中": "Đang xử lý",
    "已完成": "Hoàn tất",
    "失败": "Thất bại",
    # Theme / personal
    "浅色": "Sáng",
    "深色": "Tối",
    "使用系统设置": "Dùng cài đặt hệ thống",
    "简体中文": "Tiếng Trung (Giản thể)",
    # Orientation
    "横屏": "Ngang",
    "竖屏": "Dọc",
    # Soft/hard subtitle modes often shown
    "软字幕": "Phụ đề mềm",
    "硬字幕": "Phụ đề cứng",
    # File dialogs / filters leftover
    "音视频文件": "File audio/video",
    "字幕文件": "File phụ đề",
    "选择文件": "Chọn tệp",
    "文件不存在": "Tệp không tồn tại",
    "文件名": "Tên tệp",
    "进度": "Tiến độ",
    "状态": "Trạng thái",
}


def is_vietnamese_ui() -> bool:
    try:
        from videocaptioner.ui.common.config import Language, cfg

        return cfg.get(cfg.language) == Language.VIETNAMESE
    except Exception:
        return True


def L(text: Any) -> str:
    """Localize a display string/enum value for the current UI language."""
    if text is None:
        return ""
    if isinstance(text, Enum):
        raw = str(text.value)
    else:
        raw = str(text)
    if not is_vietnamese_ui():
        return raw
    return VI_LABELS.get(raw, raw)


def labels(options: Iterable[Any]) -> List[str]:
    """Map enum members / raw values to UI labels."""
    return [L(o) for o in options]


def unlabel(text: Any) -> str:
    """Resolve a UI label to a value Enum() can accept.

    Enum `.value` strings are Vietnamese; also accept legacy Chinese via
    Enum._missing_. Prefer identity when the text is already a current value.
    """
    raw = str(text.value) if isinstance(text, Enum) else str(text or "")
    if not is_vietnamese_ui():
        return raw
    # Already a current (Vietnamese) label — keep as-is
    if raw in VI_LABELS.values():
        return raw
    # Legacy Chinese still in settings / old UI paths
    if raw in VI_LABELS:
        return VI_LABELS[raw]
    return raw


def combo_enum(combo, enum_cls=None):
    """Get enum stored in ComboBox userData, with label fallback."""
    data = combo.currentData()
    if data is not None and (enum_cls is None or isinstance(data, enum_cls)):
        return data
    raw = unlabel(combo.currentText())
    if enum_cls is not None:
        try:
            return enum_cls(raw)
        except ValueError:
            return None
    return raw
