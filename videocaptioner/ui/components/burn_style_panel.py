"""Compact panel: font / text color / bg color for burn-in subtitles."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFontDatabase
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    ComboBox,
    CompactSpinBox,
    StrongBodyLabel,
)

from videocaptioner.ui.common.burn_subtitle_style import (
    BURN_FONT_CHOICES,
    BurnSubtitleStyle,
)
from videocaptioner.ui.components.MySettingCard import ColorPickerButton


class BurnStylePanel(QWidget):
    """Shown when user enables burning Vietnamese subtitles onto video."""

    styleChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self.set_style(BurnSubtitleStyle())

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(8)

        root.addWidget(StrongBodyLabel("Kiểu phụ đề cháy vào video", self))
        root.addWidget(
            BodyLabel(
                "Giống reup CapCut: chữ vàng + nền đen ôm chữ (đè lên sub Trung cũ).",
                self,
            )
        )

        row1 = QHBoxLayout()
        row1.setSpacing(10)

        font_col = QVBoxLayout()
        font_col.setSpacing(4)
        font_col.addWidget(BodyLabel("Font chữ", self))
        self.font_combo = ComboBox(self)
        self.font_combo.setMinimumHeight(34)
        available = set(QFontDatabase().families())
        fonts = [f for f in BURN_FONT_CHOICES if f in available]
        if not fonts:
            fonts = sorted(available)[:40] or ["Arial"]
        for name in fonts:
            self.font_combo.addItem(name)
        # Also allow any system font at end
        for name in sorted(available):
            if name not in fonts:
                self.font_combo.addItem(name)
        font_col.addWidget(self.font_combo)
        row1.addLayout(font_col, 2)

        size_col = QVBoxLayout()
        size_col.setSpacing(4)
        size_col.addWidget(BodyLabel("Cỡ chữ (0=tự động)", self))
        self.size_spin = CompactSpinBox(self)
        self.size_spin.setRange(0, 120)
        self.size_spin.setValue(0)
        self.size_spin.setMinimumHeight(34)
        size_col.addWidget(self.size_spin)
        row1.addLayout(size_col, 1)

        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        text_col.addWidget(BodyLabel("Màu chữ", self))
        self.text_color_btn = ColorPickerButton(
            QColor("#FFFF00"), "Màu chữ", self, enableAlpha=False
        )
        self.text_color_btn.setFixedSize(48, 34)
        text_col.addWidget(self.text_color_btn, 0, Qt.AlignLeft)  # type: ignore[attr-defined]
        row2.addLayout(text_col)

        bg_col = QVBoxLayout()
        bg_col.setSpacing(4)
        bg_col.addWidget(BodyLabel("Màu nền đè sub cũ", self))
        self.bg_color_btn = ColorPickerButton(
            QColor("#000000"), "Màu nền", self, enableAlpha=False
        )
        self.bg_color_btn.setFixedSize(48, 34)
        bg_col.addWidget(self.bg_color_btn, 0, Qt.AlignLeft)  # type: ignore[attr-defined]
        row2.addLayout(bg_col)

        outline_col = QVBoxLayout()
        outline_col.setSpacing(4)
        outline_col.addWidget(BodyLabel("Màu viền chữ", self))
        self.outline_color_btn = ColorPickerButton(
            QColor("#000000"), "Màu viền", self, enableAlpha=False
        )
        self.outline_color_btn.setFixedSize(48, 34)
        outline_col.addWidget(self.outline_color_btn, 0, Qt.AlignLeft)  # type: ignore[attr-defined]
        row2.addLayout(outline_col)

        op_col = QVBoxLayout()
        op_col.setSpacing(4)
        op_col.addWidget(BodyLabel("Độ đục nền (0=không nền)", self))
        self.opacity_spin = CompactSpinBox(self)
        self.opacity_spin.setRange(0, 255)
        self.opacity_spin.setValue(220)
        self.opacity_spin.setMinimumHeight(34)
        self.opacity_spin.setToolTip(
            "0 = không có nền (chỉ chữ + viền).\n"
            "220–255 = nền đặc để che sub Trung cũ."
        )
        op_col.addWidget(self.opacity_spin)
        row2.addLayout(op_col, 1)

        row2.addStretch(1)
        root.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(12)
        self.bold_check = CheckBox("In đậm", self)
        self.bold_check.setChecked(True)
        row3.addWidget(self.bold_check)

        pad_col = QVBoxLayout()
        pad_col.setSpacing(2)
        pad_col.addWidget(BodyLabel("Đệm nền quanh chữ", self))
        self.pad_spin = CompactSpinBox(self)
        self.pad_spin.setRange(2, 30)
        self.pad_spin.setValue(8)
        self.pad_spin.setMinimumHeight(34)
        pad_col.addWidget(self.pad_spin)
        row3.addLayout(pad_col)

        row3.addStretch(1)
        root.addLayout(row3)

        for w in (
            self.font_combo,
            self.size_spin,
            self.opacity_spin,
            self.pad_spin,
            self.bold_check,
        ):
            if hasattr(w, "currentIndexChanged"):
                w.currentIndexChanged.connect(lambda *_: self.styleChanged.emit())
            elif hasattr(w, "valueChanged"):
                w.valueChanged.connect(lambda *_: self.styleChanged.emit())
            elif hasattr(w, "stateChanged"):
                w.stateChanged.connect(lambda *_: self.styleChanged.emit())

        self.text_color_btn.colorChanged.connect(lambda *_: self.styleChanged.emit())
        self.bg_color_btn.colorChanged.connect(lambda *_: self.styleChanged.emit())
        self.outline_color_btn.colorChanged.connect(lambda *_: self.styleChanged.emit())

    def get_style(self) -> BurnSubtitleStyle:
        return BurnSubtitleStyle(
            font_name=self.font_combo.currentText() or "Arial Black",
            font_size=int(self.size_spin.value()),
            text_color=self.text_color_btn.color.name(QColor.HexRgb),
            outline_color=self.outline_color_btn.color.name(QColor.HexRgb),
            bg_color=self.bg_color_btn.color.name(QColor.HexRgb),
            bg_opacity=int(self.opacity_spin.value()),
            box_padding=int(self.pad_spin.value()),
            bold=self.bold_check.isChecked(),
        )

    def set_style(self, style: BurnSubtitleStyle) -> None:
        idx = self.font_combo.findText(style.font_name)
        if idx >= 0:
            self.font_combo.setCurrentIndex(idx)
        else:
            self.font_combo.addItem(style.font_name)
            self.font_combo.setCurrentText(style.font_name)
        self.size_spin.setValue(style.font_size)
        self.text_color_btn.setColor(QColor(style.text_color))
        self.bg_color_btn.setColor(QColor(style.bg_color))
        self.outline_color_btn.setColor(QColor(style.outline_color))
        self.opacity_spin.setValue(style.bg_opacity)
        self.pad_spin.setValue(style.box_padding)
        self.bold_check.setChecked(style.bold)
