"""UI options: how to handle original video audio when dubbing."""

from __future__ import annotations

from typing import Literal

from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, CompactSpinBox

OriginalAudioMode = Literal["replace", "keep_bgm", "mix", "keep_full"]

# (label, mode, default_volume_pct)
AUDIO_MODES: list[tuple[str, OriginalAudioMode, int]] = [
    ("Tắt thoại gốc, giữ nhạc nền + giọng mới", "keep_bgm", 90),
    ("Tắt hẳn âm gốc — chỉ giọng mới", "replace", 0),
    ("Giữ nguyên âm gốc nhỏ + giọng mới", "mix", 20),
    ("Giữ nguyên âm gốc (100%) + chèn giọng mới", "keep_full", 100),
]


class DubAudioOptions(QWidget):
    """Shown under “Ghép giọng” — replace / keep BGM / mix original track."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 4)
        root.setSpacing(6)

        root.addWidget(BodyLabel("Âm thanh video gốc khi ghép giọng", self))

        row = QHBoxLayout()
        row.setSpacing(10)

        self.mode_combo = ComboBox(self)
        self.mode_combo.setMinimumHeight(34)
        for label, _, _ in AUDIO_MODES:
            self.mode_combo.addItem(label)
        self.mode_combo.setCurrentIndex(0)  # keep_bgm mặc định
        self.mode_combo.setToolTip(
            "Giữ nhạc nền: cố gắng tắt thoại gốc (stereo karaoke), giữ BGM/SFX + TTS.\n"
            "Tắt hẳn: bỏ hết âm gốc, chỉ còn giọng TTS.\n"
            "Giữ nhỏ: hạ cả track gốc rồi trộn với TTS.\n"
            "Giữ nguyên 100%: giữ đúng âm gốc, chỉ chèn thêm giọng mới lên trên."
        )
        row.addWidget(self.mode_combo, 3)

        vol_col = QVBoxLayout()
        vol_col.setSpacing(2)
        self.vol_label = BodyLabel("Mức nhạc nền (%)", self)
        vol_col.addWidget(self.vol_label)
        self.vol_spin = CompactSpinBox(self)
        self.vol_spin.setRange(1, 150)
        self.vol_spin.setValue(90)
        self.vol_spin.setMinimumHeight(34)
        self.vol_spin.setToolTip("Âm lượng phần âm gốc còn giữ (nhạc nền hoặc mix).")
        vol_col.addWidget(self.vol_spin)
        row.addLayout(vol_col, 1)

        root.addLayout(row)
        root.addWidget(
            BodyLabel(
                "Khuyên dùng: “Tắt thoại gốc, giữ nhạc nền”. "
                "(Video mono / thoại lệch kênh có thể vẫn nghe sót thoại.)",
                self,
            )
        )

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._on_mode_changed(0)

    def _mode(self) -> OriginalAudioMode:
        idx = self.mode_combo.currentIndex()
        if 0 <= idx < len(AUDIO_MODES):
            return AUDIO_MODES[idx][1]
        return "keep_bgm"

    def _on_mode_changed(self, index: int) -> None:
        mode = AUDIO_MODES[index][1] if 0 <= index < len(AUDIO_MODES) else "keep_bgm"
        show_vol = mode in {"keep_bgm", "mix"}
        self.vol_spin.setVisible(show_vol)
        self.vol_label.setVisible(show_vol)
        if mode == "keep_bgm":
            self.vol_label.setText("Mức nhạc nền (%)")
            self.vol_spin.setRange(20, 150)
            self.vol_spin.setValue(AUDIO_MODES[index][2])
        elif mode == "mix":
            self.vol_label.setText("Âm gốc (%)")
            self.vol_spin.setRange(1, 80)
            self.vol_spin.setValue(AUDIO_MODES[index][2])

    def original_audio_mode(self) -> OriginalAudioMode:
        return self._mode()

    def mix_original_audio(self) -> bool:
        """Legacy: True khi còn dùng một phần âm gốc."""
        return self._mode() in {"keep_bgm", "mix", "keep_full"}

    def original_audio_volume(self) -> float:
        mode = self._mode()
        if mode == "replace":
            return 0.0
        if mode == "keep_full":
            return 1.0
        if mode == "keep_bgm":
            return max(0.2, min(1.5, self.vol_spin.value() / 100.0))
        return max(0.01, min(0.8, self.vol_spin.value() / 100.0))
