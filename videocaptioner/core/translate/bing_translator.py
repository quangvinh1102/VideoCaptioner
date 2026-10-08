"""Bing 翻译器"""

from typing import Callable, List, Optional

import requests

from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.translate.base import BaseTranslator, logger
from videocaptioner.core.translate.types import TargetLanguage, get_language_code
from videocaptioner.core.utils.cache import generate_cache_key


class BingTranslator(BaseTranslator):
    """必应翻译器"""

    AUTH_ENDPOINTS = (
        "https://edge.microsoft.com/translate/auth",
        "https://edge.microsoft.com/translate/auth/",
    )

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        target_language: TargetLanguage,
        update_callback: Optional[Callable],
    ):
        super().__init__(
            thread_num=thread_num,
            batch_num=batch_num,
            target_language=target_language,
            update_callback=update_callback,
        )
        self.timeout = 20
        self.session = requests.Session()
        self.translate_endpoint = (
            "https://api-edge.cognitive.microsofttranslator.com/translate"
        )

        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.bing.com/translator",
        }
        self._init_session()

    def _init_session(self):
        """初始化会话，获取必要的token"""
        last_error: Optional[Exception] = None
        for endpoint in self.AUTH_ENDPOINTS:
            try:
                response = self.session.get(
                    endpoint, headers=self.headers, timeout=self.timeout
                )
                response.raise_for_status()
                token = (response.text or "").strip()
                if not token or token.startswith("<"):
                    raise RuntimeError(f"Invalid Bing auth token from {endpoint}")
                self.auth_token = token
                self.headers["authorization"] = f"Bearer {self.auth_token}"
                return
            except Exception as e:
                last_error = e
                logger.warning("Bing auth endpoint failed (%s): %s", endpoint, e)
        logger.error("Failed to init Bing session: %s", last_error)
        raise RuntimeError(f"Failed to init Bing session: {last_error}")

    def _translate_chunk(
        self, subtitle_chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        """翻译字幕块"""
        target_lang = get_language_code(self.target_language, "bing")

        # 准备批量翻译的数据
        texts_to_translate = [
            {"Text": data.original_text[:5000]} for data in subtitle_chunk
        ]

        if texts_to_translate:
            try:
                params = {
                    "to": target_lang,
                    "api-version": "3.0",
                    "includeSentenceLength": "true",
                }

                response = self.session.post(
                    self.translate_endpoint,
                    params=params,
                    headers=self.headers,
                    json=texts_to_translate,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                translations = response.json()

                # 处理翻译结果
                for i, translation in enumerate(translations):
                    subtitle_chunk[i].translated_text = translation["translations"][0][
                        "text"
                    ]

            except Exception as e:
                logger.error(f"Bing translation failed: {str(e)}")
                resp = locals().get("response")
                if "token" in str(e).lower() or (
                    resp is not None
                    and getattr(resp, "status_code", None) in [401, 403]
                ):
                    try:
                        self._init_session()
                    except Exception as e:
                        logger.error(f"重新Failed to init Bing session: {str(e)}")

        return subtitle_chunk

    def _get_cache_key(self, chunk: List[SubtitleProcessData]) -> str:
        """生成缓存键"""
        class_name = self.__class__.__name__
        chunk_key = generate_cache_key(chunk)
        lang = self.target_language.value
        return f"{class_name}:{chunk_key}:{lang}"
