"""Thu âm giọng nói từ Microphone máy tính (Laptop / PC) với chất lượng cao."""

import speech_recognition as sr
from typing import Optional


def listen_from_pc_mic(timeout: float = 5.0, phrase_time_limit: float = 10.0) -> Optional[str]:
    """Lắng nghe 1 câu nói từ Microphone máy tính và nhận diện tiếng Việt.

    Returns:
        Văn bản tiếng Việt nhận diện được, hoặc None nếu không nghe thấy.
    """
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("🎙️  [Mic Máy Tính] Đang lắng nghe... Hãy nói điều bạn muốn hỏi Bủn:")
            recognizer.adjust_for_ambient_noise(source, duration=0.6)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            print("⏳ Đang nhận diện giọng nói...")
            text = recognizer.recognize_google(audio, language="vi-VN")
            return text.strip()
    except sr.WaitTimeoutError:
        print("⏱️ Hết thời gian chờ tiếng nói.")
        return None
    except sr.UnknownValueError:
        print("❓ Không nghe rõ câu nói. Vui lòng thử lại.")
        return None
    except Exception as exc:
        print(f"⚠️ Lỗi Microphone máy tính: {exc}")
        return None
