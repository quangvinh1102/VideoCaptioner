"""Load Qt Linguist .ts XML files at runtime (no lrelease required)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from PyQt5.QtCore import QTranslator


class TsTranslator(QTranslator):
    """QTranslator backed by a .ts XML file."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # (context, source) -> translation
        self._map: dict[tuple[str, str], str] = {}
        # source-only fallback
        self._source_map: dict[str, str] = {}

    def load_ts(self, path: str | Path) -> bool:
        path = Path(path)
        if not path.exists():
            return False
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except ET.ParseError:
            return False

        self._map.clear()
        self._source_map.clear()
        for context in root.findall("context"):
            name_el = context.find("name")
            ctx = (name_el.text or "") if name_el is not None else ""
            for message in context.findall("message"):
                source_el = message.find("source")
                trans_el = message.find("translation")
                if source_el is None or trans_el is None:
                    continue
                # unfinished / vanished
                if trans_el.get("type") in {"unfinished", "vanished", "obsolete"}:
                    if not (trans_el.text or "").strip():
                        continue
                source = source_el.text or ""
                translation = trans_el.text or ""
                # Preserve multiline: ElementTree may lose tails; join child text
                if list(trans_el):
                    parts = [trans_el.text or ""]
                    for child in trans_el:
                        parts.append(child.text or "")
                        parts.append(child.tail or "")
                    translation = "".join(parts)
                if not source or not translation.strip():
                    continue
                self._map[(ctx, source)] = translation
                # Prefer first context-specific entry for source-only fallback
                self._source_map.setdefault(source, translation)
        return bool(self._map)

    def translate(self, context, sourceText, disambiguation=None, n=-1):  # noqa: N802
        if not sourceText:
            return ""
        ctx = context or ""
        hit = self._map.get((ctx, sourceText))
        if hit:
            return hit
        hit = self._source_map.get(sourceText)
        if hit:
            return hit
        # PyQt: trả về sourceText khi chưa có bản dịch ("" sẽ làm menu Fluent trống chữ)
        return sourceText
