"""Local video UI: chọn file → dịch → chọn giọng → chạy pipeline."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    ComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    TextEdit,
    TitleLabel,
    ToolButton,
)

from videocaptioner.core.constant import (
    INFOBAR_DURATION_ERROR,
    INFOBAR_DURATION_INFO,
    INFOBAR_DURATION_SUCCESS,
)
from videocaptioner.core.utils.platform_utils import open_folder
from videocaptioner.ui.common.voice_catalog import (
    VOICES,
    VoiceOption,
    default_voice_index_for_lang,
)
from videocaptioner.ui.thread.quick_link_thread import QuickLinkThread
from videocaptioner.ui.thread.voice_preview import VoicePreviewPlayer
from videocaptioner.ui.view.quick_link_interface import (
    DEFAULT_OUTPUT_DIR,
    LANGUAGES,
)

VIDEO_FILTER = (
    "Video (*.mp4 *.mkv *.webm *.mov *.avi *.m4v *.flv *.ts *.mpeg *.mpg);;"
    "All files (*.*)"
)
VIDEO_EXTS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".mov",
    ".avi",
    ".m4v",
    ".flv",
    ".ts",
    ".mpeg",
    ".mpg",
}


class LocalVideoInterface(QWidget):
    """Form: upload local video + language + voice + run ASR/translate/dub."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LocalVideoInterface")
        self.setWindowTitle(self.tr("Dịch video máy"))
        self.setAcceptDrops(True)
        self._worker: QuickLinkThread | None = None
        self._last_result: str = ""
        self._voice_preview = VoicePreviewPlayer(self)

        self._build_ui()
        self._wire()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # type: ignore[attr-defined]
        self.scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QWidget#LocalVideoScroll{background:transparent;}"
        )

        self.scrollWidget = QWidget()
        self.scrollWidget.setObjectName("LocalVideoScroll")
        self.scrollWidget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum
        )

        layout = QVBoxLayout(self.scrollWidget)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(14)

        layout.addWidget(
            TitleLabel("Video máy → Dịch → Giọng Việt", self.scrollWidget)
        )
        layout.addWidget(
            BodyLabel(
                "Chọn / kéo thả video (vd. hoạt hình Trung), chọn ngôn ngữ dịch & giọng, rồi Bắt đầu.",
                self.scrollWidget,
            )
        )

        layout.addWidget(StrongBodyLabel("File video", self.scrollWidget))
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.video_edit = LineEdit(self.scrollWidget)
        self.video_edit.setPlaceholderText(
            "Kéo thả video vào đây, hoặc bấm nút chọn file..."
        )
        self.video_edit.setClearButtonEnabled(True)
        self.video_edit.setFixedHeight(36)
        self.pick_btn = ToolButton(FIF.FOLDER_ADD, self.scrollWidget)
        self.pick_btn.setFixedSize(36, 36)
        self.pick_btn.setToolTip("Chọn video trên máy")
        file_row.addWidget(self.video_edit, 1)
        file_row.addWidget(self.pick_btn)
        layout.addLayout(file_row)

        row = QHBoxLayout()
        row.setSpacing(16)

        lang_col = QVBoxLayout()
        lang_col.setSpacing(6)
        lang_col.addWidget(StrongBodyLabel("Dịch sang", self.scrollWidget))
        self.lang_combo = ComboBox(self.scrollWidget)
        self.lang_combo.setMinimumHeight(36)
        for name, _ in LANGUAGES:
            self.lang_combo.addItem(name)
        self.lang_combo.setCurrentIndex(0)
        lang_col.addWidget(self.lang_combo)
        row.addLayout(lang_col, 1)

        voice_col = QVBoxLayout()
        voice_col.setSpacing(6)
        voice_col.addWidget(StrongBodyLabel("Giọng lồng tiếng", self.scrollWidget))
        voice_row = QHBoxLayout()
        voice_row.setSpacing(8)
        self.voice_combo = ComboBox(self.scrollWidget)
        self.voice_combo.setMinimumHeight(36)
        self.voice_combo.setMaxVisibleItems(14)
        for voice in VOICES:
            self.voice_combo.addItem(voice.label)
        self.voice_combo.setCurrentIndex(0)
        self.preview_btn = PushButton(FIF.HEADPHONE, "Nghe thử", self.scrollWidget)
        self.preview_btn.setFixedHeight(36)
        self.preview_btn.setToolTip("Phát mẫu ngắn với giọng đang chọn (Edge TTS)")
        voice_row.addWidget(self.voice_combo, 1)
        voice_row.addWidget(self.preview_btn)
        voice_col.addLayout(voice_row)
        row.addLayout(voice_col, 1)

        layout.addLayout(row)

        layout.addWidget(StrongBodyLabel("Thư mục lưu kết quả", self.scrollWidget))
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.output_edit = LineEdit(self.scrollWidget)
        self.output_edit.setText(str(DEFAULT_OUTPUT_DIR))
        self.output_edit.setFixedHeight(36)
        self.browse_btn = ToolButton(FIF.FOLDER, self.scrollWidget)
        self.browse_btn.setFixedSize(36, 36)
        self.browse_btn.setToolTip("Chọn thư mục")
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(self.browse_btn)
        layout.addLayout(out_row)

        # Translation service selection
        trans_col = QVBoxLayout()
        trans_col.setSpacing(6)
        trans_col.addWidget(StrongBodyLabel("Dịch vụ dịch", self.scrollWidget))
        self.trans_combo = ComboBox(self.scrollWidget)
        self.trans_combo.setMinimumHeight(36)
        self.trans_combo.setMaxVisibleItems(8)
        self._trans_options = [
            ("Google (miễn phí)", "google"),
            ("Bing (miễn phí)", "bing"),
            ("LLM API (cần key)", "llm"),
            ("ChatGPT Web (miễn phí, chậm)", "chatgpt-web"),
        ]
        for label, _ in self._trans_options:
            self.trans_combo.addItem(label)
        self.trans_combo.setCurrentIndex(0)  # Google default
        trans_col.addWidget(self.trans_combo)
        layout.addLayout(trans_col)

        from videocaptioner.ui.components.llm_api_panel import LlmApiPanel

        self.llm_panel = LlmApiPanel(
            self.scrollWidget,
            hint="Dán key OpenRouter (sk-or-...) → tự set Base URL + tải model. Không key → Google miễn phí.",
        )
        layout.addWidget(self.llm_panel)
        self.llm_panel.hide()  # Ẩn mặc định, chỉ hiện khi chọn LLM API

        self.dub_check = CheckBox(
            "Ghép giọng vào video (TTS)", self.scrollWidget
        )
        self.dub_check.setChecked(True)
        layout.addWidget(self.dub_check)

        from videocaptioner.ui.components.dub_audio_options import DubAudioOptions

        self.dub_audio_options = DubAudioOptions(self.scrollWidget)
        layout.addWidget(self.dub_audio_options)

        self.burn_subs_check = CheckBox(
            "Cháy phụ đề Việt vào video (đè lên sub Trung cũ)",
            self.scrollWidget,
        )
        self.burn_subs_check.setChecked(True)
        self.burn_subs_check.setToolTip(
            "Bật nếu video gốc có chữ Trung cháy cứng cần che. "
            "Tắt nếu chỉ cần lồng tiếng, không cần sub trên hình."
        )
        layout.addWidget(self.burn_subs_check)

        from videocaptioner.ui.components.burn_style_panel import BurnStylePanel

        self.burn_style_panel = BurnStylePanel(self.scrollWidget)
        layout.addWidget(self.burn_style_panel)

        from videocaptioner.ui.components.logo_overlay_panel import LogoOverlayPanel

        self.logo_panel = LogoOverlayPanel(self.scrollWidget)
        layout.addWidget(self.logo_panel)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.start_btn = PrimaryPushButton(FIF.PLAY, "Bắt đầu", self.scrollWidget)
        self.cancel_btn = PushButton(FIF.CANCEL, "Hủy", self.scrollWidget)
        self.cancel_btn.setEnabled(False)
        self.open_btn = PushButton(
            FIF.FOLDER, "Mở thư mục kết quả", self.scrollWidget
        )
        self.open_btn.setEnabled(False)
        actions.addWidget(self.start_btn)
        actions.addWidget(self.cancel_btn)
        actions.addStretch(1)
        actions.addWidget(self.open_btn)
        layout.addLayout(actions)

        self.progress = ProgressBar(self.scrollWidget)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.status_label = BodyLabel(
            "Sẵn sàng — chọn video để bắt đầu.", self.scrollWidget
        )
        layout.addWidget(self.status_label)

        self.log_edit = TextEdit(self.scrollWidget)
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("Nhật ký xử lý sẽ hiện ở đây...")
        self.log_edit.setMinimumHeight(180)
        self.log_edit.setMaximumHeight(320)
        layout.addWidget(self.log_edit)
        layout.addStretch(1)

        self.scroll.setWidget(self.scrollWidget)
        root.addWidget(self.scroll)

    def _wire(self) -> None:
        self.video_edit.textChanged.connect(
            lambda t: self.logo_panel.set_video_path(t.strip().strip('"'))
        )
        self.pick_btn.clicked.connect(self._browse_video)
        self.browse_btn.clicked.connect(self._browse_output)
        self.start_btn.clicked.connect(self._start)
        self.cancel_btn.clicked.connect(self._cancel)
        self.open_btn.clicked.connect(self._open_output)
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        self.trans_combo.currentIndexChanged.connect(self._on_trans_changed)
        self._on_trans_changed(self.trans_combo.currentIndex())
        self.dub_check.stateChanged.connect(self._on_dub_toggled)
        self.burn_subs_check.stateChanged.connect(self._on_burn_toggled)
        self.burn_style_panel.styleChanged.connect(self._sync_sub_preview)
        self.preview_btn.clicked.connect(self._preview_voice)
        self._voice_preview.status.connect(self._on_preview_status)
        self._voice_preview.busy_changed.connect(self._on_preview_busy)
        self._on_burn_toggled(self.burn_subs_check.checkState())
        self._on_dub_toggled(self.dub_check.checkState())

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if Path(url.toLocalFile()).suffix.lower() in VIDEO_EXTS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
                self.video_edit.setText(str(path))
                self.logo_panel.set_video_path(str(path))
                self._append_log(f"Đã chọn: {path.name}")
                event.acceptProposedAction()
                return
        event.ignore()

    def _browse_video(self) -> None:
        start = self.video_edit.text().strip()
        start_dir = str(Path(start).parent) if start else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn video", start_dir, VIDEO_FILTER
        )
        if path:
            self.video_edit.setText(path)
            self.logo_panel.set_video_path(path)

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục lưu", self.output_edit.text()
        )
        if path:
            self.output_edit.setText(path)

    def _on_lang_changed(self, index: int) -> None:
        if index < 0 or index >= len(LANGUAGES):
            return
        lang = LANGUAGES[index][1]
        self.voice_combo.setCurrentIndex(default_voice_index_for_lang(lang))

    def _on_trans_changed(self, index: int) -> None:
        """Hiển thị/ẩn LLM API panel tùy theo dịch vụ dịch được chọn."""
        if index < 0 or index >= len(self._trans_options):
            return
        trans = self._trans_options[index][1]
        self.llm_panel.setVisible(trans == "llm")

    def _selected_voice(self) -> VoiceOption:
        idx = self.voice_combo.currentIndex()
        if idx < 0 or idx >= len(VOICES):
            return VOICES[0]
        return VOICES[idx]

    def _on_dub_toggled(self, state: int) -> None:
        enabled = state == Qt.Checked  # type: ignore[attr-defined]
        self.voice_combo.setEnabled(enabled)
        self.preview_btn.setEnabled(enabled)
        self.dub_audio_options.setEnabled(enabled)
        self.dub_audio_options.setVisible(enabled)

    def _on_burn_toggled(self, state: int) -> None:
        on = state == Qt.Checked  # type: ignore[attr-defined]
        self.burn_style_panel.setVisible(on)
        self.logo_panel.set_subtitle_preview_enabled(on)
        if on:
            self._sync_sub_preview()

    def _sync_sub_preview(self) -> None:
        self.logo_panel.set_subtitle_style(self.burn_style_panel.get_style())

    def _preview_voice(self) -> None:
        voice = self._selected_voice()
        self._append_log(
            f"Nghe thử: {voice.label} ({voice.voice_id}, {voice.rate}, {voice.pitch})"
        )
        self._voice_preview.preview(voice)

    def _on_preview_status(self, message: str) -> None:
        self.status_label.setText(message)
        self._append_log(message)

    def _on_preview_busy(self, busy: bool) -> None:
        self.preview_btn.setEnabled(
            (not busy) and self.dub_check.isChecked()
        )

    def _append_log(self, text: str) -> None:
        self.log_edit.append(text)

    def _start(self) -> None:
        video = self.video_edit.text().strip().strip('"')
        if not video:
            InfoBar.warning(
                title="Thiếu video",
                content="Hãy chọn hoặc kéo thả file video trước.",
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=INFOBAR_DURATION_INFO,
                parent=self,
            )
            return
        video_path = Path(video)
        if not video_path.is_file():
            InfoBar.warning(
                title="File không tồn tại",
                content=str(video_path),
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=INFOBAR_DURATION_INFO,
                parent=self,
            )
            return
        if video_path.suffix.lower() not in VIDEO_EXTS:
            InfoBar.warning(
                title="Định dạng không hỗ trợ",
                content=f"Phần mở rộng: {video_path.suffix}",
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=INFOBAR_DURATION_INFO,
                parent=self,
            )
            return

        out_dir = self.output_edit.text().strip()
        if not out_dir:
            InfoBar.warning(
                title="Thiếu thư mục",
                content="Hãy chọn nơi lưu kết quả.",
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=INFOBAR_DURATION_INFO,
                parent=self,
            )
            return

        lang_idx = self.lang_combo.currentIndex()
        voice = self._selected_voice()
        target_language = LANGUAGES[lang_idx][1]

        self.log_edit.clear()
        self.progress.setValue(0)
        self._last_result = ""
        self.open_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self._append_log(f"Video: {video_path}")
        self._append_log(f"Ngôn ngữ: {LANGUAGES[lang_idx][0]}")
        self._append_log(f"Giọng: {voice.label} ({voice.rate}, {voice.pitch})")
        self._append_log(f"Lưu tại: {out_dir}")

        api_key = self.llm_panel.api_key()
        api_base = self.llm_panel.api_base()
        model = self.llm_panel.model()
        use_ai = self.llm_panel.use_ai()

        trans_choice = self._trans_options[self.trans_combo.currentIndex()][1]
        use_chatgpt_web = trans_choice == "chatgpt-web"
        if use_chatgpt_web:
            use_ai = False  # ChatGPT Web không dùng LLM API key

        if self.llm_panel.ai_check.isChecked() and not api_key and not use_chatgpt_web:
            InfoBar.warning(
                title="Thiếu API key",
                content="Đã tick AI nhưng chưa nhập key — sẽ dùng Google miễn phí.",
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=INFOBAR_DURATION_INFO,
                parent=self,
            )
        if use_ai:
            self._append_log(f"AI: ON ({model} @ {api_base})")
            self.llm_panel.save_to_cfg()
        else:
            self._append_log("AI: OFF (Google miễn phí)")

        logo_err = self.logo_panel.validate()
        if logo_err:
            InfoBar.warning(
                title="Logo",
                content=logo_err,
                orient=Qt.Horizontal,  # type: ignore[attr-defined]
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=INFOBAR_DURATION_INFO,
                parent=self,
            )
            self.start_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return
        if self.logo_panel.enabled():
            self._append_log(
                f"Logo: ON {self.logo_panel.placement()} — {self.logo_panel.sticker_path()}"
            )
        else:
            self._append_log("Logo: OFF")
        self._append_log("---")

        self._worker = QuickLinkThread(
            local_video=str(video_path),
            output_dir=out_dir,
            target_language=target_language,
            voice=voice.voice_id,
            provider=voice.provider,
            edge_rate=voice.rate,
            edge_pitch=voice.pitch,
            capcut_resource_id=voice.resource_id,
            enable_dub=self.dub_check.isChecked(),
            mix_original_audio=self.dub_audio_options.mix_original_audio(),
            original_audio_volume=self.dub_audio_options.original_audio_volume(),
            original_audio_mode=self.dub_audio_options.original_audio_mode(),
            burn_subtitles=self.burn_subs_check.isChecked(),
            burn_style=self.logo_panel.merge_subtitle_style(
                self.burn_style_panel.get_style()
            ).to_dict(),
            overlay_logo=self.logo_panel.enabled(),
            logo_path=(
                self.logo_panel.sticker_path() if self.logo_panel.enabled() else None
            ),
            logo_placement=(
                self.logo_panel.placement() if self.logo_panel.enabled() else None
            ),
            llm_api_key=api_key or None,
            llm_api_base=api_base,
            llm_model=model,
            use_ai=use_ai,
            use_chatgpt_web=use_chatgpt_web,
            parent=self,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.status_label.setText("Đang hủy...")
            self._append_log("Người dùng yêu cầu hủy.")
            self.cancel_btn.setEnabled(False)

    def _on_progress(self, pct: int, message: str) -> None:
        self.progress.setValue(max(0, min(100, pct)))
        self.status_label.setText(message)
        self._append_log(f"[{pct}%] {message}")

    def _on_finished(self, result_path: str) -> None:
        self._last_result = result_path
        self.progress.setValue(100)
        self.status_label.setText("Hoàn tất!")
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.open_btn.setEnabled(True)
        self._append_log(f"Kết quả: {result_path}")
        InfoBar.success(
            title="Xong",
            content=f"Đã lưu: {result_path}",
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=INFOBAR_DURATION_SUCCESS,
            parent=self,
        )

    def _on_failed(self, message: str) -> None:
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Lỗi")
        self._append_log(f"LỖI: {message}")
        InfoBar.error(
            title="Thất bại",
            content=message[:200],
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=INFOBAR_DURATION_ERROR,
            parent=self,
        )

    def _open_output(self) -> None:
        target = self._last_result or self.output_edit.text().strip()
        if not target:
            return
        path = Path(target)
        folder = path if path.is_dir() else path.parent
        if folder.exists():
            open_folder(str(folder))
