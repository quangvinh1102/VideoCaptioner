"""UI: chọn logo + kéo vị trí trên khung xem trước video."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    LineEdit,
    PushButton,
    StrongBodyLabel,
)

from videocaptioner.core.utils.logo_overlay import (
    crop_logo_content,
    default_logo_path,
    extract_video_frame,
)
from videocaptioner.ui.components.logo_placement_canvas import LogoPlacementCanvas


class _FrameLoadThread(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path

    def run(self) -> None:
        try:
            out = Path(tempfile.gettempdir()) / "vc_logo_preview_frame.png"
            extract_video_frame(self.video_path, str(out), time_sec=1.5)
            self.finished_ok.emit(str(out))
        except Exception as exc:
            self.failed.emit(str(exc))


class LogoOverlayPanel(QWidget):
    """Enable logo overlay with interactive drag placement on a video frame."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_path: str = ""
        self._preview_image: str = ""
        self._sticker_path: str = ""
        self._frame_thread: _FrameLoadThread | None = None
        self._sub_preview_on = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(6)

        root.addWidget(
            StrongBodyLabel("Xem trước video (logo + phụ đề)", self)
        )
        self.enable_check = CheckBox(
            "Đè logo lên watermark — kéo vị trí trên khung xem trước", self
        )
        self.enable_check.setChecked(False)
        self.enable_check.setToolTip(
            "Với link: bấm «Xem trước» rồi kéo logo. Với file local: chọn video trước."
        )
        root.addWidget(self.enable_check)

        root.addWidget(StrongBodyLabel("File logo PNG", self))
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.path_edit = LineEdit(self)
        self.path_edit.setFixedHeight(36)
        default = default_logo_path()
        if default.is_file():
            self.path_edit.setText(str(default))
        self.path_edit.setPlaceholderText(str(default))
        path_row.addWidget(self.path_edit, 1)
        self.browse_btn = PushButton("Chọn…", self)
        self.browse_btn.setFixedHeight(36)
        path_row.addWidget(self.browse_btn)
        self.reload_btn = PushButton("Tải lại khung", self)
        self.reload_btn.setFixedHeight(36)
        self.reload_btn.setToolTip("Lấy lại 1 frame từ video để đặt logo / xem sub")
        path_row.addWidget(self.reload_btn)
        root.addLayout(path_row)

        self.canvas = LogoPlacementCanvas(self)
        root.addWidget(self.canvas)

        self.status_label = BodyLabel(
            "Link: bấm «Xem trước» · File local: chọn video → kéo logo (xanh) / phụ đề (vàng).",
            self,
        )
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.browse_btn.clicked.connect(self._browse)
        self.reload_btn.clicked.connect(self._reload_frame)
        self.enable_check.stateChanged.connect(self._on_toggle)
        self.path_edit.editingFinished.connect(self._load_logo)
        self._on_toggle(self.enable_check.checkState())
        if default.is_file():
            self._load_logo()

    def _has_preview_source(self) -> bool:
        if self._preview_image and Path(self._preview_image).is_file():
            return True
        return bool(self._video_path and Path(self._video_path).is_file())

    def _on_toggle(self, state: int) -> None:
        on = state == Qt.Checked  # type: ignore[attr-defined]
        self.path_edit.setEnabled(on)
        self.browse_btn.setEnabled(on)
        self.canvas.set_logo_interactive(on)
        self._refresh_preview_visibility()
        if (on or self._sub_preview_on) and self._has_preview_source():
            self._reload_frame()

    def _refresh_preview_visibility(self) -> None:
        show = self.enabled() or self._sub_preview_on
        self.canvas.setVisible(show)
        self.status_label.setVisible(show)
        self.reload_btn.setEnabled(show and self._has_preview_source())

    def ensure_preview_visible(self) -> None:
        """Force-show canvas after an external thumbnail load."""
        self.canvas.setVisible(True)
        self.status_label.setVisible(True)
        self.reload_btn.setEnabled(self._has_preview_source())

    def set_subtitle_style(self, style) -> None:
        """Sync burn-subtitle style into live preview (giữ vị trí đã kéo)."""
        self.canvas.set_subtitle_style(style, keep_position=True)

    def set_subtitle_preview_enabled(self, enabled: bool) -> None:
        self._sub_preview_on = bool(enabled)
        self.canvas.set_subtitle_preview(self._sub_preview_on)
        self._refresh_preview_visibility()
        if self._sub_preview_on and self._has_preview_source():
            self._reload_frame()

    def subtitle_placement(self) -> dict:
        return self.canvas.subtitle_placement()

    def merge_subtitle_style(self, style):
        """Copy dragged subtitle position onto a BurnSubtitleStyle."""
        place = self.subtitle_placement()
        style.pos_x_pct = float(place.get("x_pct", 0.5))
        style.pos_y_pct = float(place.get("y_pct", 0.92))
        return style

    def _browse(self) -> None:
        start = self.path_edit.text().strip() or str(default_logo_path().parent)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file logo PNG",
            start,
            "PNG (*.png);;All files (*.*)",
        )
        if path:
            self.path_edit.setText(path)
            self._load_logo()

    def _load_logo(self) -> None:
        path = Path(self.logo_path())
        if not path.is_file():
            self.status_label.setText(f"Không tìm thấy logo: {path}")
            return
        try:
            sticker = crop_logo_content(str(path))
            self._sticker_path = str(sticker)
            pix = QPixmap(str(sticker))
            self.canvas.set_logo_pixmap(pix)
            self.canvas.set_placement({"x_pct": 0.70, "y_pct": 0.02, "w_pct": 0.26})
            self.status_label.setText(
                "Kéo logo tới chỗ watermark. Kéo góc xanh / lăn chuột để đổi cỡ."
            )
        except Exception as exc:
            self.status_label.setText(f"Lỗi load logo: {exc}")

    def set_video_path(self, video_path: str) -> None:
        """Load a preview frame when user picks a local video."""
        path = (video_path or "").strip().strip('"')
        self._video_path = path
        self._preview_image = ""
        if not path or not Path(path).is_file():
            self.canvas.set_frame_pixmap(QPixmap())
            self.status_label.setText("Chưa có video — chọn file để hiện khung đặt logo.")
            self._refresh_preview_visibility()
            return
        self._reload_frame()

    def set_preview_image(self, image_path: str, *, note: str = "") -> None:
        """Use a remote thumbnail / still image as placement canvas (no local video yet)."""
        path = (image_path or "").strip().strip('"')
        self._preview_image = path
        # Keep video path empty so we don't try ffmpeg extract on a jpg
        if path and Path(path).is_file():
            self._video_path = ""
            pix = QPixmap(path)
            if pix.isNull():
                self.status_label.setText(f"Không đọc được ảnh preview: {path}")
                return
            self.canvas.set_frame_pixmap(pix)
            self._refresh_preview_visibility()
            suffix = f" — {note}" if note else ""
            if self.canvas.has_logo():
                self.status_label.setText(
                    f"Ảnh preview đã sẵn{suffix}. Kéo logo (xanh) / phụ đề (vàng), rồi Bắt đầu."
                )
            else:
                self.status_label.setText(
                    f"Ảnh preview đã sẵn{suffix}. Kéo phụ đề (vàng); tick đè logo nếu cần."
                )
            return
        self.canvas.set_frame_pixmap(QPixmap())
        self.status_label.setText("Chưa có ảnh preview.")
        self._refresh_preview_visibility()

    def _reload_frame(self) -> None:
        if self._preview_image and Path(self._preview_image).is_file():
            self.set_preview_image(self._preview_image)
            return
        path = self._video_path
        if not path or not Path(path).is_file():
            self.status_label.setText(
                "Chưa có khung xem trước — với link hãy bấm «Xem trước»."
            )
            return
        self.status_label.setText("Đang lấy frame video...")
        if self._frame_thread and self._frame_thread.isRunning():
            return
        self._frame_thread = _FrameLoadThread(path, self)
        self._frame_thread.finished_ok.connect(self._on_frame_ready)
        self._frame_thread.failed.connect(
            lambda e: self.status_label.setText(f"Lỗi lấy frame: {e}")
        )
        self._frame_thread.start()

    def _on_frame_ready(self, frame_path: str) -> None:
        pix = QPixmap(frame_path)
        self.canvas.set_frame_pixmap(pix)
        if self.canvas.has_logo():
            self.status_label.setText(
                "Kéo logo (xanh) hoặc kéo phụ đề (vàng) trên khung → rồi Bắt đầu."
            )
        else:
            self.status_label.setText(
                "Đã có khung — kéo phụ đề (viền vàng). Tick đè logo nếu cần kéo logo."
            )

    def enabled(self) -> bool:
        return self.enable_check.isChecked()

    def logo_path(self) -> str:
        text = self.path_edit.text().strip().strip('"')
        if text:
            return text
        return str(default_logo_path())

    def sticker_path(self) -> str:
        """Cropped logo used for overlay (falls back to original)."""
        if self._sticker_path and Path(self._sticker_path).is_file():
            return self._sticker_path
        return self.logo_path()

    def placement(self) -> dict:
        return self.canvas.placement()

    def validate(self, *, require_frame: bool = True) -> str | None:
        if not self.enabled():
            return None
        path = Path(self.logo_path())
        if not path.is_file():
            return f"Không tìm thấy logo: {path}"
        if path.suffix.lower() not in {".png", ".webp", ".gif"}:
            return "Logo nên là PNG nền trong suốt"
        if require_frame:
            if not self.canvas.has_frame():
                return (
                    "Chưa có khung xem trước — với link bấm «Xem trước»; "
                    "với file local chọn video rồi «Tải lại khung»."
                )
        return None
