"""Đọc và quản lý cấu hình từ biến môi trường qua python-dotenv."""

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Tìm và nạp file .env từ thư mục gốc của dự án
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Cấu hình ứng dụng."""

    # Gemini API
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    # Camera RTSP
    CAMERA_RTSP_URL: str = os.getenv("CAMERA_RTSP_URL", "").strip()

    # Giới hạn kích thước ảnh
    MAX_IMAGE_WIDTH: int = 1280
    JPEG_QUALITY: int = 85

    # Giới hạn bộ nhớ hội thoại
    MAX_CONVERSATION_TURNS: int = 10

    def validate(self) -> list[str]:
        """Kiểm tra các biến môi trường bắt buộc, trả về danh sách lỗi nếu có."""
        errors: list[str] = []
        if not self.GEMINI_API_KEY:
            errors.append(
                "Thiếu GEMINI_API_KEY trong file .env. Hãy tạo key tại https://aistudio.google.com/"
            )
        if not self.CAMERA_RTSP_URL:
            errors.append(
                "Thiếu CAMERA_RTSP_URL trong file .env. Vui lòng cấu hình URL RTSP của camera."
            )
        return errors


settings = Settings()
