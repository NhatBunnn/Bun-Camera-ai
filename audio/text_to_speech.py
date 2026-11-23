"""Chuyển đổi văn bản thành giọng nói tiếng Việt tự nhiên qua Edge-TTS và phát ra loa."""

import asyncio
import io
import logging
import os
import tempfile
import pygame

logger = logging.getLogger(__name__)

# Giọng đọc tiếng Việt tự nhiên của Microsoft Edge TTS
DEFAULT_VOICE = "vi-VN-HoaiMyNeural"  # Giọng nữ ấm áp, tự nhiên


async def _synthesize_edge_tts(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """Tạo file âm thanh MP3 từ văn bản dùng Edge-TTS."""
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    audio_buffer = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_buffer.extend(chunk["data"])
    return bytes(audio_buffer)


def speak_text(text: str, voice: str = DEFAULT_VOICE) -> None:
    """Tạo giọng nói từ văn bản và phát ra loa ngay lập tức.

    Args:
        text: Văn bản câu trả lời từ Bủn.
        voice: Mã giọng đọc (mặc định: vi-VN-HoaiMyNeural).
    """
    if not text or not text.strip():
        return

    try:
        # Tạo dữ liệu âm thanh MP3
        audio_bytes = asyncio.run(_synthesize_edge_tts(text.strip(), voice))

        # Lưu vào file tạm an toàn để pygame phát
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(audio_bytes)

        # Khởi tạo và phát qua pygame mixer
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        # Áp dụng mức âm lượng
        from camera.volume import volume_controller
        vol_fraction = max(0.05, min(1.0, volume_controller.get_volume() / 100.0))
        pygame.mixer.music.set_volume(vol_fraction)

        pygame.mixer.music.load(temp_path)
        pygame.mixer.music.play()

        # Đợi phát xong
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        pygame.mixer.music.unload()

        # Dọn dẹp file tạm
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass

    except Exception as exc:
        logger.error("Lỗi khi phát giọng nói TTS: %s", exc)
        print(f"⚠️ [TTS] Không thể phát âm thanh: {exc}")
