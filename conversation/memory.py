"""Quản lý lịch sử hội thoại và bộ nhớ đệm ảnh gần nhất cho Bun Camera AI."""

from dataclasses import dataclass, field
from typing import Any, List, Optional
from google.genai import types

from config.settings import settings


@dataclass
class MessageTurn:
    """Lưu trữ một lượt hội thoại giữa Người dùng và Bủn."""

    user_text: str
    model_text: str
    image_bytes: Optional[bytes] = None


class ConversationMemory:
    """Quản lý bộ nhớ phiên trò chuyện:

    - Duy trì lịch sử tối đa N lượt hội thoại gần nhất (mặc định 8-10 lượt).
    - Lưu trữ hình ảnh gần nhất để phục vụ các câu hỏi nối tiếp.
    - Chuyển đổi lịch sử thành danh sách `types.Content` tương thích với SDK google-genai.
    """

    def __init__(self, max_turns: Optional[int] = None):
        self.max_turns = max_turns or settings.MAX_CONVERSATION_TURNS
        self.turns: List[MessageTurn] = []
        self._last_image_bytes: Optional[bytes] = None

    @property
    def last_image_bytes(self) -> Optional[bytes]:
        """Lấy dữ liệu ảnh chụp gần nhất trong phiên."""
        return self._last_image_bytes

    @last_image_bytes.setter
    def last_image_bytes(self, image_data: bytes) -> None:
        """Cập nhật ảnh chụp gần nhất."""
        self._last_image_bytes = image_data

    def has_image(self) -> bool:
        """Kiểm tra xem trong phiên đã có ảnh chụp nào từ camera chưa."""
        return self._last_image_bytes is not None

    def add_turn(
        self,
        user_text: str,
        model_text: str,
        image_bytes: Optional[bytes] = None,
    ) -> None:
        """Ghi nhận thêm một lượt hội thoại hoàn tất và cập nhật cửa sổ trượt."""
        if image_bytes is not None:
            self._last_image_bytes = image_bytes

        self.turns.append(
            MessageTurn(
                user_text=user_text,
                model_text=model_text,
                image_bytes=image_bytes,
            )
        )

        # Cắt tỉa theo cửa sổ trượt (sliding window) để giữ tối đa max_turns lượt
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

    def build_contents_payload(
        self,
        current_user_text: str,
        current_image_bytes: Optional[bytes] = None,
        reuse_last_image: bool = False,
    ) -> list[types.Content]:
        """Tạo danh sách types.Content cho cuộc gọi Gemini API bao gồm:

        1. Lịch sử các lượt trước (text & hình ảnh đính kèm nếu có).
        2. Lượt hội thoại hiện tại (user text + ảnh mới hoặc ảnh tái sử dụng nếu cần).
        """
        contents: list[types.Content] = []

        # 1. Thêm lịch sử các lượt trước
        for turn in self.turns:
            user_parts: list[types.Part] = []
            if turn.image_bytes is not None:
                user_parts.append(
                    types.Part.from_bytes(
                        data=turn.image_bytes, mime_type="image/jpeg"
                    )
                )
            user_parts.append(types.Part.from_text(text=turn.user_text))

            contents.append(types.Content(role="user", parts=user_parts))
            contents.append(
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=turn.model_text)],
                )
            )

        # 2. Thêm lượt của câu hỏi hiện tại
        current_parts: list[types.Part] = []

        if current_image_bytes is not None:
            current_parts.append(
                types.Part.from_bytes(
                    data=current_image_bytes, mime_type="image/jpeg"
                )
            )
        elif reuse_last_image and self._last_image_bytes is not None:
            # Nếu câu hỏi hiện tại yêu cầu ngữ cảnh ảnh gần nhất nhưng không chụp ảnh mới,
            # và nếu trong các lượt lịch sử chưa có lượt nào mang ảnh đó, có thể đính kèm
            has_image_in_history = any(t.image_bytes is not None for t in self.turns)
            if not has_image_in_history:
                current_parts.append(
                    types.Part.from_bytes(
                        data=self._last_image_bytes, mime_type="image/jpeg"
                    )
                )

        current_parts.append(types.Part.from_text(text=current_user_text))
        contents.append(types.Content(role="user", parts=current_parts))

        return contents

    def clear(self) -> None:
        """Xóa toàn bộ lịch sử và ảnh đã lưu."""
        self.turns.clear()
        self._last_image_bytes = None
