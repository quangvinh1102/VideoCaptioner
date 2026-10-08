"""Burn-in subtitle style for covering Chinese hardsubs (CapCut reup look)."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class BurnSubtitleStyle:
    """Visual style for hard-burned Vietnamese subtitles."""

    font_name: str = "Arial Black"
    # 0 = auto-scale from video height
    font_size: int = 0
    text_color: str = "#FFFF00"  # vàng kiểu reup CapCut
    outline_color: str = "#000000"
    bg_color: str = "#000000"
    # 0 = trong suốt, 255 = đặc hoàn toàn
    bg_opacity: int = 220
    outline_width: float = 2.5
    box_padding: int = 8
    bold: bool = True
    margin_v_ratio: float = 0.045
    # Vị trí tâm khung sub trên video (0–1), kéo trên preview
    pos_x_pct: float = 0.5
    pos_y_pct: float = 0.92

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "BurnSubtitleStyle":
        if not data:
            return cls()
        from dataclasses import fields

        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


def hex_to_ass_bgr(hex_color: str, opacity: int = 255) -> str:
    """Convert #RRGGBB + opacity(0-255 opaque) → ASS &HAABBGGRR.

    ASS alpha: 00 = opaque, FF = transparent.
    """
    raw = (hex_color or "#FFFFFF").lstrip("#")
    if len(raw) == 8:
        raw = raw[:6]
    if len(raw) != 6:
        raw = "FFFFFF"
    r = int(raw[0:2], 16)
    g = int(raw[2:4], 16)
    b = int(raw[4:6], 16)
    opacity = max(0, min(255, int(opacity)))
    ass_alpha = 255 - opacity
    return f"&H{ass_alpha:02X}{b:02X}{g:02X}{r:02X}"


def build_ass_style_block(style: BurnSubtitleStyle, video_height: int) -> str:
    """Build [V4+ Styles] for burn-in subtitles.

    bg_opacity > 0 → BorderStyle=3 (ô nền ôm chữ).
    bg_opacity = 0 → BorderStyle=1 (không nền, chỉ chữ + viền).
    """
    font_size = style.font_size
    if font_size <= 0:
        font_size = max(36, int(video_height * 0.05))
    bold = -1 if style.bold else 0

    primary = hex_to_ass_bgr(style.text_color, 255)
    outline_c = hex_to_ass_bgr(style.outline_color, 255)
    back = hex_to_ass_bgr(style.bg_color, style.bg_opacity)
    font = (style.font_name or "Arial").replace(",", " ")

    if int(style.bg_opacity) <= 0:
        # Không nền: outline = độ dày viền chữ
        border_style = 1
        outline = max(1.0, float(style.outline_width))
    else:
        # Có nền: Outline = đệm ô quanh chữ
        border_style = 3
        outline = max(3, int(style.box_padding))

    return (
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Default,{font},{font_size},"
        f"{primary},&H000000FF,{outline_c},{back},"
        f"{bold},0,0,0,100,100,0,0,{border_style},{outline},0,5,40,40,0,1"
    )


def ass_pos_override(style: BurnSubtitleStyle, video_width: int, video_height: int) -> str:
    """ASS override tag: center subtitle at style.pos_* percentages."""
    x = int(max(0, min(1, float(style.pos_x_pct))) * video_width)
    y = int(max(0, min(1, float(style.pos_y_pct))) * video_height)
    return f"{{\\an5\\pos({x},{y})}}"


def inject_ass_pos(ass_content: str, pos_tag: str) -> str:
    """Prefix dialogue text with \\pos so all lines use the preview placement."""
    if not pos_tag:
        return ass_content
    out_lines: list[str] = []
    for line in ass_content.splitlines(keepends=True):
        if line.startswith("Dialogue:"):
            # Format: Dialogue: Layer,Start,End,Style,Name,ML,MR,MV,Effect,Text
            parts = line.rstrip("\r\n").split(",", 9)
            if len(parts) >= 10:
                text = parts[9]
                if not text.startswith("{") or "\\pos(" not in text[:40]:
                    parts[9] = pos_tag + text
                line = ",".join(parts) + ("\n" if line.endswith("\n") else "")
        out_lines.append(line)
    return "".join(out_lines)


# Fonts commonly available on Windows that look good for reup caps
BURN_FONT_CHOICES: list[str] = [
    "Arial Black",
    "Arial",
    "Impact",
    "Tahoma",
    "Segoe UI",
    "Segoe UI Black",
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "Verdana",
    "Trebuchet MS",
    "Comic Sans MS",
]
