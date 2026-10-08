"""Interactive video-frame canvas: drag logo + live subtitle style preview."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QTextOption,
)
from PyQt5.QtWidgets import QLabel, QSizePolicy, QWidget

from videocaptioner.ui.common.burn_subtitle_style import BurnSubtitleStyle

HANDLE = 12
SAMPLE_SUB_TEXT = "LOẠI PHẾ VẬT NÀY CÓ TƯ CÁCH GÌ Ở LẠI TÔNG MÔN?"


class LogoPlacementCanvas(QWidget):
    """Preview a video frame: drag/resize logo + live burn-subtitle preview."""

    placementChanged = pyqtSignal()
    subtitlePlacementChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.setMaximumHeight(420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)  # type: ignore[attr-defined]

        self._frame = QPixmap()
        self._logo = QPixmap()
        self._frame_draw = QRect()

        self.x_pct = 0.68
        self.y_pct = 0.02
        self.w_pct = 0.28

        self._drag_mode: Optional[str] = None  # move | resize | sub_move
        self._drag_origin = QPoint()
        self._origin_x = 0.0
        self._origin_y = 0.0
        self._origin_w = 0.0
        self._origin_sub_x = 0.5
        self._origin_sub_y = 0.92

        self._sub_style = BurnSubtitleStyle()
        self._sub_preview = True
        self._sub_text = SAMPLE_SUB_TEXT
        self._logo_interactive = True
        self._sub_box = QRect()  # last drawn subtitle box (widget coords)

        self._hint = QLabel(
            "Chọn video → kéo logo / kéo phụ đề trên khung xem trước",
            self,
        )
        self._hint.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        self._hint.setStyleSheet("color: #888; padding: 24px;")

    def has_frame(self) -> bool:
        return not self._frame.isNull()

    def has_logo(self) -> bool:
        return not self._logo.isNull()

    def set_frame_pixmap(self, pix: QPixmap) -> None:
        self._frame = pix
        self._hint.setVisible(pix.isNull())
        self._relayout()
        self.update()

    def set_logo_pixmap(self, pix: QPixmap) -> None:
        self._logo = pix
        if not pix.isNull() and self.w_pct <= 0:
            self.w_pct = 0.28
        self.update()
        self.placementChanged.emit()

    def set_logo_interactive(self, enabled: bool) -> None:
        self._logo_interactive = bool(enabled)
        self.update()

    def set_subtitle_style(
        self, style: BurnSubtitleStyle | None, *, keep_position: bool = True
    ) -> None:
        old_x = self._sub_style.pos_x_pct
        old_y = self._sub_style.pos_y_pct
        self._sub_style = style or BurnSubtitleStyle()
        if keep_position:
            self._sub_style.pos_x_pct = old_x
            self._sub_style.pos_y_pct = old_y
        self.update()

    def set_subtitle_preview(self, enabled: bool, text: str | None = None) -> None:
        self._sub_preview = bool(enabled)
        if text:
            self._sub_text = text
        self.update()

    def subtitle_placement(self) -> dict:
        return {
            "x_pct": round(float(self._sub_style.pos_x_pct), 5),
            "y_pct": round(float(self._sub_style.pos_y_pct), 5),
        }

    def set_subtitle_placement(self, data: dict | None) -> None:
        if not data:
            return
        self._sub_style.pos_x_pct = float(data.get("x_pct", self._sub_style.pos_x_pct))
        self._sub_style.pos_y_pct = float(data.get("y_pct", self._sub_style.pos_y_pct))
        self._clamp_sub()
        self.update()
        self.subtitlePlacementChanged.emit()

    def placement(self) -> dict:
        return {
            "x_pct": round(float(self.x_pct), 5),
            "y_pct": round(float(self.y_pct), 5),
            "w_pct": round(float(self.w_pct), 5),
        }

    def set_placement(self, data: dict | None) -> None:
        if not data:
            return
        self.x_pct = float(data.get("x_pct", self.x_pct))
        self.y_pct = float(data.get("y_pct", self.y_pct))
        self.w_pct = float(data.get("w_pct", self.w_pct))
        self._clamp()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()
        self._hint.setGeometry(self.rect())

    def _relayout(self) -> None:
        if self._frame.isNull():
            self._frame_draw = QRect()
            return
        fw, fh = self._frame.width(), self._frame.height()
        if fw <= 0 or fh <= 0:
            return
        area = self.rect().adjusted(4, 4, -4, -4)
        scale = min(area.width() / fw, area.height() / fh)
        dw, dh = int(fw * scale), int(fh * scale)
        x = area.x() + (area.width() - dw) // 2
        y = area.y() + (area.height() - dh) // 2
        self._frame_draw = QRect(x, y, dw, dh)

    def _logo_rect(self) -> QRect:
        fr = self._frame_draw
        if fr.isEmpty():
            return QRect()
        lw = max(24, int(fr.width() * self.w_pct))
        if not self._logo.isNull() and self._logo.width() > 0:
            lh = max(16, int(lw * self._logo.height() / self._logo.width()))
        else:
            lh = max(16, int(lw * 0.35))
        lx = fr.x() + int(fr.width() * self.x_pct)
        ly = fr.y() + int(fr.height() * self.y_pct)
        return QRect(lx, ly, lw, lh)

    def _handle_rect(self, logo_r: QRect) -> QRect:
        return QRect(
            logo_r.right() - HANDLE // 2,
            logo_r.bottom() - HANDLE // 2,
            HANDLE,
            HANDLE,
        )

    def _clamp(self) -> None:
        self.w_pct = max(0.05, min(0.95, self.w_pct))
        max_x = max(0.0, 1.0 - self.w_pct)
        aspect = (
            self._logo.height() / self._logo.width()
            if not self._logo.isNull() and self._logo.width()
            else 0.35
        )
        h_pct = self.w_pct * aspect
        max_y = max(0.0, 1.0 - h_pct)
        self.x_pct = max(0.0, min(max_x, self.x_pct))
        self.y_pct = max(0.0, min(max_y, self.y_pct))

    def _clamp_sub(self) -> None:
        self._sub_style.pos_x_pct = max(0.05, min(0.95, float(self._sub_style.pos_x_pct)))
        self._sub_style.pos_y_pct = max(0.05, min(0.95, float(self._sub_style.pos_y_pct)))

    def _measure_sub_box(self, fr: QRect) -> tuple[QRect, str, QFont, int]:
        """Return (box_rect in widget coords, display text, font, pad)."""
        style = self._sub_style
        if style.font_size and style.font_size > 0:
            font_px = max(11, int(style.font_size * fr.height() / 720))
        else:
            font_px = max(12, int(fr.height() * 0.05))

        font = QFont(style.font_name or "Arial Black")
        font.setPixelSize(font_px)
        font.setBold(bool(style.bold))
        fm = QFontMetrics(font)

        max_text_w = int(fr.width() * 0.86)
        words = self._sub_text.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            trial = f"{cur} {w}".strip()
            if fm.horizontalAdvance(trial) <= max_text_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if not lines:
            lines = [self._sub_text]
        lines = lines[:3]
        display = "\n".join(lines)

        pad = max(3, int(style.box_padding * fr.height() / 720))
        line_h = fm.height()
        text_w = max(fm.horizontalAdvance(ln) for ln in lines)
        text_h = line_h * len(lines) + fm.leading() * max(0, len(lines) - 1)
        box_w = text_w + pad * 2
        box_h = text_h + pad * 2

        cx = fr.x() + int(fr.width() * style.pos_x_pct)
        cy = fr.y() + int(fr.height() * style.pos_y_pct)
        box = QRect(cx - box_w // 2, cy - box_h // 2, box_w, box_h)
        # keep inside frame
        if box.left() < fr.left():
            box.moveLeft(fr.left())
        if box.right() > fr.right():
            box.moveRight(fr.right())
        if box.top() < fr.top():
            box.moveTop(fr.top())
        if box.bottom() > fr.bottom():
            box.moveBottom(fr.bottom())
        return box, display, font, pad

    def _draw_subtitle_preview(self, painter: QPainter, fr: QRect) -> None:
        if not self._sub_preview or fr.isEmpty():
            return
        style = self._sub_style
        box, display, font, pad = self._measure_sub_box(fr)
        self._sub_box = QRect(box)
        painter.setFont(font)

        bg = QColor(style.bg_color or "#000000")
        bg.setAlpha(max(0, min(255, int(style.bg_opacity))))
        painter.setPen(Qt.NoPen)  # type: ignore[attr-defined]
        if bg.alpha() > 0:
            painter.setBrush(bg)
            painter.drawRoundedRect(box, 3, 3)
        else:
            painter.setBrush(Qt.NoBrush)  # type: ignore[attr-defined]

        # selection border when previewing (draggable)
        painter.setBrush(Qt.NoBrush)  # type: ignore[attr-defined]
        painter.setPen(QPen(QColor(255, 200, 0), 2, Qt.DashLine))  # type: ignore[attr-defined]
        painter.drawRect(box)

        text_color = QColor(style.text_color or "#FFFF00")
        outline = QColor(style.outline_color or "#000000")
        stroke = max(1, int(max(1.0, style.outline_width) * fr.height() / 720))

        text_rect = QRectF(
            box.x() + pad,
            box.y() + pad,
            box.width() - pad * 2,
            box.height() - pad * 2,
        )
        opt = QTextOption()
        opt.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)  # type: ignore[attr-defined]
        opt.setWrapMode(QTextOption.WordWrap)

        painter.setPen(
            QPen(outline, stroke * 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)  # type: ignore[attr-defined]
        )
        for dx, dy in (
            (-stroke, 0),
            (stroke, 0),
            (0, -stroke),
            (0, stroke),
            (-stroke, -stroke),
            (stroke, -stroke),
            (-stroke, stroke),
            (stroke, stroke),
        ):
            painter.drawText(text_rect.translated(dx, dy), display, opt)

        painter.setPen(text_color)
        painter.drawText(text_rect, display, opt)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if self._frame.isNull():
            return

        self._relayout()
        fr = self._frame_draw
        painter.drawPixmap(fr, self._frame)

        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawRect(fr.adjusted(0, 0, -1, -1))

        self._draw_subtitle_preview(painter, fr)

        if self._logo_interactive and not self._logo.isNull():
            lr = self._logo_rect()
            painter.setOpacity(0.95)
            painter.drawPixmap(lr, self._logo)
            painter.setOpacity(1.0)

            painter.setPen(QPen(QColor(0, 180, 255), 2, Qt.DashLine))  # type: ignore[attr-defined]
            painter.setBrush(Qt.NoBrush)  # type: ignore[attr-defined]
            painter.drawRect(lr)
            hr = self._handle_rect(lr)
            painter.setBrush(QColor(0, 180, 255))
            painter.setPen(Qt.NoPen)  # type: ignore[attr-defined]
            painter.drawRect(hr)

        painter.setPen(QColor(220, 220, 220))
        hints = []
        if self._logo_interactive and not self._logo.isNull():
            hints.append(
                f"Logo ({self.x_pct:.0%},{self.y_pct:.0%},w={self.w_pct:.0%})"
            )
        if self._sub_preview:
            hints.append(
                f"Sub kéo được ({self._sub_style.pos_x_pct:.0%},{self._sub_style.pos_y_pct:.0%})"
            )
        painter.drawText(8, self.height() - 8, " · ".join(hints) or "Preview")

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.LeftButton or self._frame.isNull():  # type: ignore[attr-defined]
            return
        pos = event.pos()
        lr = self._logo_rect() if self._logo_interactive and not self._logo.isNull() else QRect()
        hr = self._handle_rect(lr) if not lr.isEmpty() else QRect()

        # Logo handle / body first (trên watermark), rồi mới tới sub
        if not hr.isEmpty() and hr.contains(pos):
            self._drag_mode = "resize"
        elif not lr.isEmpty() and lr.contains(pos):
            self._drag_mode = "move"
        elif self._sub_preview and not self._sub_box.isEmpty() and self._sub_box.contains(pos):
            self._drag_mode = "sub_move"
        else:
            return

        self._drag_origin = pos
        self._origin_x = self.x_pct
        self._origin_y = self.y_pct
        self._origin_w = self.w_pct
        self._origin_sub_x = self._sub_style.pos_x_pct
        self._origin_sub_y = self._sub_style.pos_y_pct
        if self._drag_mode == "resize":
            self.setCursor(Qt.SizeFDiagCursor)  # type: ignore[attr-defined]
        else:
            self.setCursor(Qt.ClosedHandCursor)  # type: ignore[attr-defined]

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.pos()
        lr = self._logo_rect() if self._logo_interactive and not self._logo.isNull() else QRect()
        if self._drag_mode is None:
            if not lr.isEmpty() and self._handle_rect(lr).contains(pos):
                self.setCursor(Qt.SizeFDiagCursor)  # type: ignore[attr-defined]
            elif not lr.isEmpty() and lr.contains(pos):
                self.setCursor(Qt.OpenHandCursor)  # type: ignore[attr-defined]
            elif self._sub_preview and not self._sub_box.isEmpty() and self._sub_box.contains(pos):
                self.setCursor(Qt.SizeAllCursor)  # type: ignore[attr-defined]
            else:
                self.setCursor(Qt.ArrowCursor)  # type: ignore[attr-defined]
            return

        fr = self._frame_draw
        if fr.isEmpty():
            return
        dx = pos.x() - self._drag_origin.x()
        dy = pos.y() - self._drag_origin.y()
        if self._drag_mode == "move":
            self.x_pct = self._origin_x + dx / fr.width()
            self.y_pct = self._origin_y + dy / fr.height()
            self._clamp()
            self.update()
            self.placementChanged.emit()
        elif self._drag_mode == "resize":
            self.w_pct = self._origin_w + dx / fr.width()
            self._clamp()
            self.update()
            self.placementChanged.emit()
        elif self._drag_mode == "sub_move":
            self._sub_style.pos_x_pct = self._origin_sub_x + dx / fr.width()
            self._sub_style.pos_y_pct = self._origin_sub_y + dy / fr.height()
            self._clamp_sub()
            self.update()
            self.subtitlePlacementChanged.emit()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_mode = None
        self.setCursor(Qt.ArrowCursor)  # type: ignore[attr-defined]

    def wheelEvent(self, event) -> None:  # noqa: N802
        if (
            not self._logo_interactive
            or self._logo.isNull()
            or self._frame.isNull()
        ):
            return
        delta = event.angleDelta().y()
        step = 0.02 if delta > 0 else -0.02
        self.w_pct += step
        self._clamp()
        self.update()
        self.placementChanged.emit()
