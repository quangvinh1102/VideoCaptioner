"""ChatGPT Web Translator — Dịch thuật qua ChatGPT web (chat.openai.com).

Sử dụng Playwright để tự động hóa trình duyệt, gửi batch subtitle
vào ChatGPT web và nhận kết quả dịch.

Ưu điểm:
- Miễn phí (dùng tài khoản ChatGPT hiện có)
- Không cần API Key
- Chất lượng dịch tốt (GPT-4o mini)

Nhược điểm:
- Chậm hơn API (cần đợi browser render)
- Giới hạn số tin nhắn/ngày (Free: ~15-30, Plus: ~80-120)
- Cần đăng nhập tài khoản ChatGPT
"""

import json
import re
import time
from typing import Callable, List, Optional

from videocaptioner.core.entities import SubtitleProcessData
from videocaptioner.core.prompts import get_prompt
from videocaptioner.core.translate.base import BaseTranslator, logger
from videocaptioner.core.translate.types import TargetLanguage
from videocaptioner.core.utils.cache import generate_cache_key


class ChatGPTWebTranslator(BaseTranslator):
    """ChatGPT Web Translator — Dịch qua chat.openai.com bằng Playwright.

    Hoạt động:
    1. Mở trình duyệt headless
    2. Đăng nhập vào ChatGPT (nếu cần)
    3. Gửi batch subtitle dạng prompt
    4. Nhận kết quả dịch
    5. Parse và trả về

    Attributes:
        batch_size: Số dòng subtitle mỗi batch (mặc định 30)
        delay_between_batches: Thời gian chờ giữa các batch (giây)
        max_retries: Số lần retry tối đa khi thất bại
        headless: Chạy trình duyệt ẩn (mặc định True)
    """

    DEFAULT_BATCH_SIZE = 30
    DEFAULT_DELAY = 35  # Giây, để tránh rate limit
    DEFAULT_MAX_RETRIES = 3
    MAX_OUTPUT_TOKENS = 4000  # Giới hạn output của GPT-4o mini

    def __init__(
        self,
        thread_num: int,
        batch_num: int,
        target_language: TargetLanguage,
        update_callback: Optional[Callable] = None,
        headless: bool = True,
        delay_between_batches: int = DEFAULT_DELAY,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        # ChatGPT web không hỗ trợ đa luồng (cùng 1 session)
        super().__init__(
            thread_num=1,
            batch_num=batch_num,
            target_language=target_language,
            update_callback=update_callback,
        )
        self.headless = headless
        self.delay_between_batches = delay_between_batches
        self.max_retries = max_retries
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._is_initialized = False

    def _init_browser(self):
        """Khởi tạo Playwright browser và đăng nhập ChatGPT."""
        if self._is_initialized:
            return

        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
        except ImportError:
            raise RuntimeError(
                "Playwright is required for ChatGPT Web Translator. "
                "Install it with: pip install playwright && playwright install chromium"
            )

        logger.info("Initializing ChatGPT Web Translator...")
        try:
            if self._playwright is None:
                self._playwright = sync_playwright().start()
            
            if self._context is None:
                from pathlib import Path
                
                # Tạo thư mục lưu profile riêng để giữ trạng thái đăng nhập
                profile_dir = Path.home() / ".videocaptioner" / "playwright_profile"
                profile_dir.mkdir(parents=True, exist_ok=True)
                
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 720},
                )
                self._browser = self._context.browser  # Có thể None với persistent context
                
            if self._page is None:
                # Persistent context mặc định mở sẵn 1 trang
                self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

            # Đi đến ChatGPT
            logger.info("Navigating to chat.openai.com...")
            self._page.goto("https://chat.openai.com", wait_until="networkidle", timeout=60000)

            # Kiểm tra nếu cần đăng nhập
            if self._page.locator('button:has-text("Log in")').count() > 0:
                logger.warning(
                    "ChatGPT requires login. Please log in manually in the browser window. "
                    "Waiting for login (max 120s)..."
                )
                # Chờ người dùng đăng nhập
                self._page.wait_for_url("https://chat.openai.com/**", timeout=120000)

            # Đợi trang load xong
            self._page.wait_for_timeout(3000)
            self._is_initialized = True
            logger.info("ChatGPT Web Translator initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            self.stop()
            raise e

    def _ensure_browser(self):
        """Đảm bảo browser đã được khởi tạo."""
        if not self._is_initialized:
            self._init_browser()

    def _translate_chunk(
        self, subtitle_chunk: List[SubtitleProcessData]
    ) -> List[SubtitleProcessData]:
        """Dịch một batch subtitle qua ChatGPT web.

        Args:
            subtitle_chunk: Danh sách subtitle cần dịch

        Returns:
            Danh sách subtitle đã dịch
        """
        self._ensure_browser()

        # Chuẩn bị prompt
        subtitle_dict = {str(data.index): data.original_text for data in subtitle_chunk}
        prompt = self._build_prompt(subtitle_dict)

        # Gửi và nhận kết quả với retry
        response_text = self._send_with_retry(prompt)

        # Parse kết quả
        translated_dict = self._parse_response(response_text, subtitle_dict)

        # Fill kết quả vào subtitle_chunk
        for data in subtitle_chunk:
            data.translated_text = translated_dict.get(str(data.index), data.original_text)

        return subtitle_chunk

    def _build_prompt(self, subtitle_dict: dict) -> str:
        """Xây dựng prompt để gửi đến ChatGPT.

        Args:
            subtitle_dict: Dict {index: text}

        Returns:
            Prompt string
        """
        # Sử dụng prompt template từ hệ thống
        system_prompt = get_prompt(
            "translate/standard",
            target_language=self.target_language.value,
            custom_prompt="",
        )

        # Format subtitle thành JSON
        subtitle_json = json.dumps(subtitle_dict, ensure_ascii=False, indent=2)

        # Kết hợp prompt và thêm câu lệnh ép buộc ở cuối cùng để ChatGPT không bị nhầm lẫn
        full_prompt = (
            f"{system_prompt}\n\n"
            f"<subtitles>\n{subtitle_json}\n</subtitles>\n\n"
            f"Please strictly translate the text inside <subtitles> into {self.target_language.value} "
            f"and output ONLY the valid JSON dictionary matching the <output_format>."
        )

        return full_prompt

    def _send_with_retry(self, prompt: str) -> str:
        """Gửi prompt đến ChatGPT web với retry logic.

        Args:
            prompt: Prompt cần gửi

        Returns:
            Response text từ ChatGPT

        Raises:
            RuntimeError: Nếu tất cả retry đều thất bại
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = self._send_message(prompt)
                if response:
                    return response
            except Exception as e:
                last_error = e
                logger.warning(
                    f"ChatGPT web translation attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    wait_time = self.delay_between_batches * (attempt + 1)
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)

        raise RuntimeError(
            f"ChatGPT web translation failed after {self.max_retries} attempts: {last_error}"
        )

    def _send_message(self, prompt: str) -> str:
        """Gửi tin nhắn đến ChatGPT web và nhận response.

        Args:
            prompt: Nội dung tin nhắn

        Returns:
            Response text từ ChatGPT
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        # Tìm textarea để nhập
        textarea = self._page.locator('textarea[data-id="root"], textarea#prompt-textarea, div[contenteditable="true"]').first

        if textarea.count() == 0:
            raise RuntimeError("Cannot find ChatGPT input textarea")

        # Nhập prompt
        textarea.click()
        self._page.wait_for_timeout(500)

        # Xóa nội dung cũ (nếu có)
        textarea.fill("")
        self._page.wait_for_timeout(200)

        # Nhập nội dung mới
        textarea.fill(prompt)
        self._page.wait_for_timeout(1000)

        # Tìm nút gửi
        send_button = self._page.locator('button[data-testid="send-button"], button[aria-label="Send message"]').first

        if send_button.count() == 0:
            # Thử nhấn Enter
            textarea.press("Enter")
        else:
            send_button.click()

        # Đợi response
        logger.info("Waiting for ChatGPT response...")

        # Đợi response xuất hiện (tối đa 120 giây)
        try:
            # Đợi response cuối cùng
            response_selector = '[data-message-role="assistant"]'
            self._page.wait_for_selector(response_selector, timeout=120000)

            # Đợi thêm chút để đảm bảo response đã hoàn tất
            self._page.wait_for_timeout(2000)

            # Lấy tất cả response
            responses = self._page.locator(response_selector)
            last_response = responses.last.inner_text()

            return last_response

        except PlaywrightTimeout:
            raise RuntimeError("Timeout waiting for ChatGPT response (120s)")

    def _parse_response(self, response_text: str, original_dict: dict) -> dict:
        """Parse response từ ChatGPT thành dict {index: translated_text}.

        Args:
            response_text: Response text từ ChatGPT
            original_dict: Dict gốc {index: text}

        Returns:
            Dict {index: translated_text}
        """
        # Thử parse JSON trước
        try:
            # Tìm JSON trong response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, dict):
                    # Validate keys
                    expected_keys = set(original_dict.keys())
                    actual_keys = set(str(k) for k in parsed.keys())
                    if expected_keys == actual_keys:
                        return {str(k): str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: parse theo số dòng
        lines = response_text.strip().split("\n")
        result = {}
        idx = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Tìm pattern "1. text" hoặc "1: text" hoặc "1. text"
            match = re.match(r'^(\d+)[.:\)]\s*(.+)$', line)
            if match:
                key = match.group(1)
                value = match.group(2).strip()
                result[key] = value
            else:
                # Nếu không có số, gán theo thứ tự
                keys = list(original_dict.keys())
                if idx < len(keys):
                    result[keys[idx]] = line
                    idx += 1

        # Nếu vẫn thiếu, thử parse theo format khác
        if len(result) < len(original_dict):
            # Fallback: chia đều theo số dòng
            all_lines = [l.strip() for l in lines if l.strip()]
            keys = list(original_dict.keys())
            for i, key in enumerate(keys):
                if i < len(all_lines):
                    result[key] = all_lines[i]

        return result

    def _get_cache_key(self, chunk: List[SubtitleProcessData]) -> str:
        """Tạo cache key."""
        class_name = self.__class__.__name__
        chunk_key = generate_cache_key(chunk)
        lang = self.target_language.value
        return f"{class_name}:{chunk_key}:{lang}"

    def stop(self):
        """Dừng translator và đóng browser."""
        super().stop()
        if self._context:
            try:
                self._context.close()
            except Exception as e:
                logger.error(f"Error closing context: {e}")
            finally:
                self._context = None

        if self._browser:
            try:
                self._browser.close()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
            finally:
                self._browser = None

        if self._page:
            self._page = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                logger.error(f"Error stopping playwright: {e}")
            finally:
                self._playwright = None

        self._is_initialized = False
        logger.info("ChatGPT Web Translator stopped.")

    def __del__(self):
        """Destructor để đảm bảo đóng browser."""
        self.stop()
