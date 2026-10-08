"""LLM API panel: paste key → auto-detect base URL → load model list."""

from __future__ import annotations

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CheckBox,
    EditableComboBox,
    LineEdit,
    PasswordLineEdit,
    StrongBodyLabel,
)

from videocaptioner.core.llm.check_llm import get_available_models
from videocaptioner.ui.common.config import cfg

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
OPENAI_BASE = "https://api.openai.com/v1"

# Gợi ý model phổ biến khi chưa load được list
FALLBACK_MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash",
    "anthropic/claude-3.5-sonnet",
    "deepseek/deepseek-chat",
    "gpt-4o-mini",
    "gpt-4o",
]


def detect_api_base(api_key: str, current_base: str = "") -> str:
    """Guess API base from key prefix when base is empty/default."""
    key = (api_key or "").strip()
    base = (current_base or "").strip()
    if key.startswith("sk-or-"):
        return OPENROUTER_BASE
    if base and base not in ("", OPENAI_BASE):
        return base
    if key.startswith("sk-"):
        return OPENAI_BASE
    return base or OPENAI_BASE


class _LoadModelsThread(QThread):
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, api_base: str, api_key: str, parent=None):
        super().__init__(parent)
        self.api_base = api_base
        self.api_key = api_key

    def run(self) -> None:
        try:
            models = get_available_models(self.api_base, self.api_key)
            self.finished_ok.emit(models or [])
        except Exception as exc:
            self.failed.emit(str(exc))


class LlmApiPanel(QWidget):
    """Checkbox + API key + base URL + model combo (auto-load on key paste)."""

    modelsLoaded = pyqtSignal(int)
    statusChanged = pyqtSignal(str)

    def __init__(self, parent=None, hint: str | None = None):
        super().__init__(parent)
        self._load_thread: _LoadModelsThread | None = None
        self._debounce = None
        self._build(hint or "")
        self._wire()
        self._restore_from_cfg()

    def _build(self, hint: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        root.addWidget(
            StrongBodyLabel("API Key AI (tuỳ chọn — tối ưu & dịch tốt hơn)", self)
        )
        self.ai_check = CheckBox("Bật AI hỗ trợ (LLM) khi có API key", self)
        root.addWidget(self.ai_check)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        self.api_key_edit = PasswordLineEdit(self)
        self.api_key_edit.setPlaceholderText(
            "Dán API key (OpenRouter / OpenAI / proxy) — tự load model"
        )
        self.api_key_edit.setFixedHeight(36)
        key_row.addWidget(self.api_key_edit, 1)
        root.addLayout(key_row)

        base_row = QHBoxLayout()
        base_row.setSpacing(8)
        self.api_base_edit = LineEdit(self)
        self.api_base_edit.setPlaceholderText("API Base URL (tự điền nếu OpenRouter)")
        self.api_base_edit.setFixedHeight(36)
        base_row.addWidget(self.api_base_edit, 1)
        root.addLayout(base_row)

        model_row = QHBoxLayout()
        model_row.setSpacing(8)
        self.model_combo = EditableComboBox(self)
        self.model_combo.setPlaceholderText("Model — tự load sau khi dán key")
        self.model_combo.setMinimumHeight(36)
        for name in FALLBACK_MODELS:
            self.model_combo.addItem(name)
        model_row.addWidget(self.model_combo, 1)
        root.addLayout(model_row)

        self.status_label = BodyLabel(
            hint
            or "Dán key OpenRouter (sk-or-...) → tự set Base URL + tải danh sách model.",
            self,
        )
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

    def _wire(self) -> None:
        from PyQt5.QtCore import QTimer

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(700)
        self._debounce.timeout.connect(self._load_models)

        self.api_key_edit.textChanged.connect(self._on_key_changed)
        self.api_base_edit.editingFinished.connect(self._schedule_load)
        self.ai_check.stateChanged.connect(self._on_ai_toggled)

    def _restore_from_cfg(self) -> None:
        key = (cfg.get(cfg.openai_api_key) or "").strip()
        base = (cfg.get(cfg.openai_api_base) or "").strip() or OPENAI_BASE
        model = (cfg.get(cfg.openai_model) or "").strip() or "gpt-4o-mini"

        if key:
            self.api_key_edit.setText(key)
            self.ai_check.setChecked(True)
        self.api_base_edit.setText(detect_api_base(key, base) if key else base)
        self._set_model_text(model)
        if key:
            self._schedule_load()

    def _on_ai_toggled(self, state: int) -> None:
        enabled = state == Qt.Checked  # type: ignore[attr-defined]
        self.api_key_edit.setEnabled(True)
        self.api_base_edit.setEnabled(enabled or bool(self.api_key()))
        self.model_combo.setEnabled(enabled or bool(self.api_key()))

    def _on_key_changed(self, text: str) -> None:
        key = (text or "").strip()
        if key:
            if not self.ai_check.isChecked():
                self.ai_check.setChecked(True)
            # Tự điền OpenRouter base khi nhận diện key
            if key.startswith("sk-or-"):
                self.api_base_edit.setText(OPENROUTER_BASE)
            elif not self.api_base_edit.text().strip():
                self.api_base_edit.setText(detect_api_base(key))
        self._schedule_load()

    def _schedule_load(self) -> None:
        if self._debounce:
            self._debounce.start()

    def _load_models(self) -> None:
        api_key = self.api_key()
        if not api_key:
            self._set_status("Chưa có API key — dịch Google miễn phí.")
            return

        api_base = detect_api_base(api_key, self.api_base_edit.text())
        if self.api_base_edit.text().strip() != api_base:
            self.api_base_edit.setText(api_base)

        if self._load_thread and self._load_thread.isRunning():
            try:
                self._load_thread.finished_ok.disconnect(self._on_models_loaded)
                self._load_thread.failed.disconnect(self._on_models_failed)
            except TypeError:
                pass

        self._set_status(f"Đang tải danh sách model từ {api_base}...")
        self._load_thread = _LoadModelsThread(api_base, api_key, self)
        self._load_thread.finished_ok.connect(self._on_models_loaded)
        self._load_thread.failed.connect(self._on_models_failed)
        self._load_thread.start()

    def _on_models_loaded(self, models: list) -> None:
        prev = self.model()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if not models:
            for name in FALLBACK_MODELS:
                self.model_combo.addItem(name)
            self._set_model_text(prev or FALLBACK_MODELS[0])
            self._set_status(
                "Không lấy được list model (API có thể chặn /models). "
                "Hãy chọn/gõ model thủ công (OpenRouter: openai/gpt-4o-mini)."
            )
        else:
            for name in models:
                self.model_combo.addItem(name)
            if prev and prev in models:
                self._set_model_text(prev)
            else:
                self._set_model_text(models[0])
            self._set_status(f"Đã tải {len(models)} model — chọn model rồi Bắt đầu.")
            self.modelsLoaded.emit(len(models))
        self.model_combo.blockSignals(False)

    def _on_models_failed(self, message: str) -> None:
        self._set_status(f"Lỗi tải model: {message}")

    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)
        self.statusChanged.emit(text)

    def _set_model_text(self, text: str) -> None:
        if not text:
            return
        idx = self.model_combo.findText(text)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setCurrentText(text)

    def api_key(self) -> str:
        return self.api_key_edit.text().strip()

    def api_base(self) -> str:
        return (
            self.api_base_edit.text().strip()
            or detect_api_base(self.api_key())
            or OPENAI_BASE
        )

    def model(self) -> str:
        return self.model_combo.currentText().strip() or "gpt-4o-mini"

    def use_ai(self) -> bool:
        return self.ai_check.isChecked() and bool(self.api_key())

    def save_to_cfg(self) -> None:
        if not self.use_ai():
            return
        try:
            cfg.set(cfg.openai_api_key, self.api_key())
            cfg.set(cfg.openai_api_base, self.api_base())
            cfg.set(cfg.openai_model, self.model())
        except Exception:
            pass
