"""Giao tiếp với Gemini API thông qua SDK google-genai mới nhất."""

import logging
import time
from typing import List, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError

from ai.prompts import BUN_SYSTEM_INSTRUCTION
from config.settings import settings
from conversation.memory import ConversationMemory

logger = logging.getLogger(__name__)

# Tắt các thông báo INFO nội bộ của thư viện google-genai để terminal sạch sẽ
logging.getLogger("google_genai").setLevel(logging.WARNING)

# Danh sách candidate models tối ưu cho Vision & Text theo thứ tự ưu tiên
CANDIDATE_MODELS: List[str] = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
]


class GeminiServiceError(Exception):
    """Ngoại lệ chung cho các lỗi giao tiếp với Gemini API."""

    pass


class GeminiVisionAssistant:
    """Lớp giao tiếp chính với Gemini Vision API:

    - Sử dụng SDK `google-genai` mới nhất.
    - Hỗ trợ cơ chế tự động Retry và Fallback model khi máy chủ Google quá tải (503).
    - Định hình nhân vật trợ lý Bủn bằng System Instruction.
    - Hỗ trợ text chat và đa phương thức (image + text) kèm lịch sử đàm thoại.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        system_instruction: str = BUN_SYSTEM_INSTRUCTION,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise GeminiServiceError(
                "Chưa thiết lập GEMINI_API_KEY. Vui lòng thêm vào file .env"
            )

        self.primary_model = model_name or settings.GEMINI_MODEL
        self.system_instruction = system_instruction

        # Xây dựng danh sách model thử nghiệm theo thứ tự ưu tiên
        models_to_try = [self.primary_model]
        for candidate in CANDIDATE_MODELS:
            if candidate not in models_to_try:
                models_to_try.append(candidate)
        self.candidate_models = models_to_try

        try:
            self.client = genai.Client(api_key=self.api_key)
        except Exception as exc:
            raise GeminiServiceError(
                f"Không thể khởi tạo Gemini Client: {str(exc)}"
            ) from exc

    def ask(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        memory: Optional[ConversationMemory] = None,
        reuse_last_image: bool = False,
    ) -> str:
        """Gửi yêu cầu tới Gemini và nhận phản hồi văn bản, tự động retry & fallback nếu quá tải."""
        # Chuẩn bị contents (kèm lịch sử)
        if memory is not None:
            contents = memory.build_contents_payload(
                current_user_text=prompt,
                current_image_bytes=image_bytes,
                reuse_last_image=reuse_last_image,
            )
        else:
            parts: list[types.Part] = []
            if image_bytes is not None:
                parts.append(
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")
                )
            parts.append(types.Part.from_text(text=prompt))
            contents = [types.Content(role="user", parts=parts)]

        # Cấu hình sinh nội dung
        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            temperature=0.7,
            max_output_tokens=300,
        )

        last_error = None

        # Thử lần lượt các model trong danh sách (kèm retry khi gặp 503)
        for model in self.candidate_models:
            for attempt in range(2):
                try:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )

                    if not response.text:
                        return "Em chưa nhìn rõ hoặc chưa nghe kịp, bạn nói lại giúp em nhé."

                    reply_text = response.text.strip()

                    # Ghi nhận lượt hội thoại thành công
                    if memory is not None:
                        memory.add_turn(
                            user_text=prompt,
                            model_text=reply_text,
                            image_bytes=image_bytes,
                        )

                    return reply_text

                except APIError as api_err:
                    error_msg = str(api_err)
                    last_error = api_err

                    # Nếu lỗi 503 (quá tải tạm thời), đợi 1.5s rồi thử lại 1 lần nữa trước khi đổi model
                    if "503" in error_msg or "UNAVAILABLE" in error_msg:
                        if attempt == 0:
                            time.sleep(1.5)
                            continue
                        break

                    # Nếu là 404 (model không hỗ trợ trên tài khoản), chuyển sang model tiếp theo
                    if "404" in error_msg or "NOT_FOUND" in error_msg:
                        break

                    if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                        raise GeminiServiceError(
                            "Đã vượt quá hạn mức truy vấn Gemini API (Quota Exceeded). Vui lòng thử lại sau ít phút."
                        ) from api_err

                    if "API_KEY_INVALID" in error_msg or "401" in error_msg:
                        raise GeminiServiceError(
                            "GEMINI_API_KEY không hợp lệ. Vui lòng kiểm tra lại file .env."
                        ) from api_err

                    raise GeminiServiceError(
                        f"Lỗi từ Gemini API: {api_err.message if hasattr(api_err, 'message') else error_msg}"
                    ) from api_err

                except Exception as exc:
                    last_error = exc
                    break

        raise GeminiServiceError(
            f"Máy chủ Gemini AI hiện đang bận. Vui lòng thử lại sau giây lát. (Chi tiết: {last_error})"
        )
