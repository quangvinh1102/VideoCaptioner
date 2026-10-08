"""Google 翻译器 — dùng endpoint GTX ổn định (không cần key)."""

from __future__ import annotations

import html
import re
import threading
import time
from typing import Callable, List, Optional

import requests

from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.translate.base import BaseTranslator, logger
from videocaptioner.core.translate.types import TargetLanguage, get_language_code
from videocaptioner.core.utils.cache import generate_cache_key


class GoogleTranslator(BaseTranslator):
    """谷歌翻译器"""

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        target_language: TargetLanguage,
        timeout: int,
        update_callback: Optional[Callable],
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            update_callback=update_callback,
        )
        self.timeout = timeout
        self.gtx_endpoint = "https://translate.googleapis.com/translate_a/single"
        self.mobile_endpoint = "https://translate.google.com/m"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        }
        self._local = threading.local()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def _translate_chunk(
        self, subtitle_chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        """翻译字幕块"""
        target_lang = get_language_code(self.target_language, "google")

        for data in subtitle_chunk:
            text = (data.original_text or "")[:5000]
            if not text.strip():
                continue
            try:
                translated = self._translate_text(text, target_lang)
                if translated:
                    data.translated_text = translated
                else:
                    logger.warning("Google returned empty translation: %s", data.index)
            except Exception as e:
                logger.error("Google translation failed %s: %s", data.index, e)

        return subtitle_chunk

    def _translate_text(self, text: str, target_lang: str) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                response = self._session().get(
                    self.gtx_endpoint,
                    params={
                        "client": "gtx",
                        "sl": "auto",
                        "tl": target_lang,
                        "dt": "t",
                        "q": text,
                    },
                    headers=self.headers,
                    timeout=self.timeout,
                )
                if response.status_code in (429, 503):
                    time.sleep(0.8 * attempt)
                    continue
                response.raise_for_status()
                payload = response.json()
                parts = [seg[0] for seg in (payload[0] or []) if seg and seg[0]]
                if parts:
                    return html.unescape("".join(parts)).strip()
            except Exception as e:
                last_error = e
                time.sleep(0.4 * attempt)

        # Mobile HTML scrape fallback
        try:
            response = self._session().get(
                self.mobile_endpoint,
                params={"tl": target_lang, "sl": "auto", "q": text},
                headers=self.headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            match = re.findall(
                r'(?s)class="(?:t0|result-container)">(.*?)<', response.text
            )
            if match:
                return html.unescape(match[0]).strip()
        except Exception as e:
            last_error = e

        if last_error:
            logger.warning("Google translate failed after retries: %s", last_error)
        return ""

    def _get_cache_key(self, chunk: List[SubtitleProcessData]) -> str:
        class_name = self.__class__.__name__
        chunk_key = generate_cache_key(chunk)
        lang = self.target_language.value
        return f"{class_name}:{chunk_key}:{lang}"
