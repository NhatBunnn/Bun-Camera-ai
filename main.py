"""Bun Camera AI - Trợ lý thông minh gia đình gắn với Camera quan sát.

Phase 1 & Phase 2: Camera Vision + Text Chat đa lượt thông minh.
Phase 3: Tự động đàm thoại 2 chiều với Loa và Mic của Camera Tiandy.
Bonus: Điều khiển xoay camera PTZ & Điều chỉnh âm lượng & Chụp và lưu ảnh vào folder.
"""

import re
import sys
import threading
from typing import Optional, Tuple

from ai.gemini import GeminiServiceError, GeminiVisionAssistant
from audio.camera_listener import CameraAudioError, CameraAudioListener
from audio.camera_speaker import play_on_camera_speaker
from audio.pc_listener import listen_from_pc_mic
from audio.text_to_speech import speak_text
from camera.ptz import ptz_controller
from camera.snapshot import CameraConnectionError, capture_latest_frame, save_snapshot_to_disk
from camera.volume import volume_controller
from config.settings import settings
from conversation.memory import ConversationMemory

# Từ khóa nhận diện yêu cầu chụp ảnh và lưu lại
CAPTURE_INTENT_KEYWORDS = [
    "chụp ảnh", "chụp hình", "chụp lại", "chụp tấm", "chụp bức",
    "lưu ảnh", "chụp một kiểu", "chụp đi", "chụp giúp", "chụp cho anh",
    "chụp cho em", "chụp cho tôi", "take photo", "capture", "chụp"
]

# Từ khóa nhận diện lệnh xoay camera
PTZ_KEYWORDS = {
    "trái": ["quay sang trái", "xoay trái", "nhìn sang trái", "bên trái", "quay trái", "ngó sang trái"],
    "phải": ["quay sang phải", "xoay phải", "nhìn sang phải", "bên phải", "quay phải", "ngó sang phải"],
    "lên": ["ngước lên", "xoay lên", "nhìn lên", "quay lên", "lên trên", "hướng lên"],
    "xuống": ["cúi xuống", "xoay xuống", "nhìn xuống", "quay xuống", "dưới sàn", "dưới đất", "hướng xuống"],
}

# Từ khóa nhận diện yêu cầu nhảy múa
DANCE_KEYWORDS = [
    "nhảy múa", "nhảy đi", "múa đi", "nhảy cho", "múa cho",
    "biết nhảy", "biết múa", "múa một bài", "nhảy một bài",
    "lắc lư", "dance", "nhảy nhót", "múa hát"
]

# Danh sách từ khóa thể hiện ý định muốn quan sát thời gian thực qua camera
REALTIME_VISION_KEYWORDS = [
    "thấy gì",
    "nhìn",
    "xem",
    "chụp",
    "có ai",
    "ở đâu",
    "đang làm gì",
    "trong phòng",
    "ngoài cửa",
    "trên bàn",
    "dưới đất",
    "ai đang",
    "ai đây",
    "ai đấy",
    "vật gì",
    "đồ gì",
    "quanh đây",
    "đằng kia",
    "bên cạnh",
    "trước mặt",
    "trước camera",
    "bây giờ",
    "hiện tại",
    "có thấy",
    "ai vào",
    "phòng khách",
]

# Từ khóa hỏi tiếp về đối tượng trong bức ảnh đã có
FOLLOW_UP_KEYWORDS = [
    "màu gì",
    "cái gì",
    "nó",
    "cái đó",
    "chiếc đó",
    "người đó",
    "thế còn",
    "ở vị trí nào",
    "bên cạnh nó",
    "để làm gì",
    "to hay nhỏ",
]


def is_explicit_capture_request(prompt: str) -> bool:
    """Kiểm tra xem câu nói có phải yêu cầu chụp ảnh và lưu lại không."""
    text = prompt.lower().strip()
    return any(kw in text for kw in CAPTURE_INTENT_KEYWORDS)


def detect_dance_intent(prompt: str) -> bool:
    """Kiểm tra xem câu nói có yêu cầu nhảy múa không."""
    text = prompt.lower().strip()
    return any(kw in text for kw in DANCE_KEYWORDS)


def perform_dance(enable_voice: bool = True) -> str:
    """Thực hiện màn vũ đạo lắc lư camera kết hợp giọng hát líu lo của Bủn."""
    dance_msg = "La la la la~ Bủn đang biểu diễn nhảy múa cho cả nhà xem nè! Lắc sang trái, nhún sang phải, ngước lên cao rồi cúi chào cả nhà nha!"
    print("\n💃 [Vũ đạo Bủn] Bắt đầu màn nhảy múa lắc lư camera...")
    print(f"💬 Bủn: {dance_msg}\n")

    dance_thread = threading.Thread(target=ptz_controller.dance)
    dance_thread.start()

    if enable_voice:
        if not play_on_camera_speaker(dance_msg):
            speak_text(dance_msg)

    dance_thread.join()
    print("✨ [Vũ đạo Bủn] Màn biểu diễn hoàn tất!\n")
    return dance_msg


def detect_ptz_intent(prompt: str) -> Optional[str]:
    """Nhận diện ý định điều khiển xoay camera trong câu nói tự nhiên."""
    text = prompt.lower().strip()

    action_words = [
        "xoay", "quay", "nhìn", "ngó", "lia", "hướng", "chuyển", "chiếu",
        "ngước", "ngẩng", "cúi", "rẽ", "quẹo", "move", "turn", "pan", "tilt", "xem"
    ]
    has_action = any(v in text for v in action_words)

    is_left = any(w in text for w in ["trái", "trai", "left"])
    is_right = any(w in text for w in ["phải", "phai", "right"])
    is_up = any(w in text for w in ["lên", "len", "trên", "tren", "up", "ngước", "nguoc", "ngẩng", "cao"])
    is_down = any(w in text for w in ["xuống", "xuong", "dưới", "duoi", "down", "cúi", "cui", "đất", "sàn", "thấp"])

    if has_action or text.startswith(("trái", "phải", "lên", "xuống", "trên", "dưới")):
        if is_left:
            return "trái"
        if is_right:
            return "phải"
        if is_up:
            return "lên"
        if is_down:
            return "xuống"

    if "sang trái" in text or "qua trái" in text or "bên trái" in text:
        return "trái"
    if "sang phải" in text or "qua phải" in text or "bên phải" in text:
        return "phải"
    if "lên trên" in text or "hướng lên" in text:
        return "lên"
    if "xuống dưới" in text or "hướng xuống" in text:
        return "xuống"

    return None


def detect_volume_intent(prompt: str) -> Optional[Tuple[str, Optional[int]]]:
    """Nhận diện yêu cầu điều chỉnh âm lượng trong câu nói tự nhiên."""
    text = prompt.lower().strip()

    match_set = re.search(r'(?:âm lượng|volume)\s*(?:là|lên|thành|về)?\s*(\d+)', text)
    if match_set:
        val = int(match_set.group(1))
        return ("set", val)

    increase_keywords = [
        "tăng âm lượng", "nói to lên", "nói lớn lên", "bật to lên",
        "to hơn", "cho to lên", "nói to hơn", "lớn hơn", "to tiếng"
    ]
    if any(kw in text for kw in increase_keywords):
        return ("increase", None)

    decrease_keywords = [
        "giảm âm lượng", "nói nhỏ lại", "nhỏ tiếng", "cho nhỏ lại",
        "nói bé lại", "nhỏ hơn", "bé hơn", "bật nhỏ lại", "bé tiếng"
    ]
    if any(kw in text for kw in decrease_keywords):
        return ("decrease", None)

    return None


def determine_vision_mode(prompt: str, memory: ConversationMemory) -> Tuple[bool, bool]:
    """Phân tích nội dung câu hỏi để quyết định chế độ xử lý hình ảnh."""
    text = prompt.lower().strip()

    has_realtime_keyword = any(kw in text for kw in REALTIME_VISION_KEYWORDS)
    has_followup_keyword = any(kw in text for kw in FOLLOW_UP_KEYWORDS)

    if has_realtime_keyword:
        return True, False

    if has_followup_keyword and memory.has_image():
        return False, True

    if has_followup_keyword and not memory.has_image():
        return True, False

    return False, False


def process_query_and_reply(
    prompt: str,
    assistant: GeminiVisionAssistant,
    memory: ConversationMemory,
    enable_voice: bool = True,
) -> str:
    """Xử lý câu hỏi, chụp và lưu ảnh vào folder nếu yêu cầu, xoay camera, hỏi Gemini và phát loa."""
    # 1. Kiểm tra yêu cầu nhảy múa
    if detect_dance_intent(prompt):
        return perform_dance(enable_voice=enable_voice)

    # 2. Kiểm tra yêu cầu điều chỉnh âm lượng
    vol_intent = detect_volume_intent(prompt)
    if vol_intent:
        action, val = vol_intent
        new_vol = 90
        if action == "set" and val is not None:
            new_vol = volume_controller.set_volume(val)
        elif action == "increase":
            new_vol = volume_controller.increase_volume(20)
        elif action == "decrease":
            new_vol = volume_controller.decrease_volume(20)

        confirm_msg = f"Em đã chỉnh âm lượng loa camera thành {new_vol}% rồi anh nhé!"
        print(f"🔊 [Âm lượng] Đã điều chỉnh âm lượng loa Camera thành: {new_vol}%\n")
        print(f"💬 Bủn: {confirm_msg}\n")
        if enable_voice:
            if not play_on_camera_speaker(confirm_msg):
                speak_text(confirm_msg)
        return confirm_msg

    # 3. Kiểm tra yêu cầu xoay camera
    ptz_direction = detect_ptz_intent(prompt)
    if ptz_direction:
        print(f"🔄 [PTZ] Phát hiện yêu cầu xoay camera hướng: {ptz_direction.upper()}...")
        success = ptz_controller.move(ptz_direction, duration=1.0, speed=0.55)
        if success:
            print(f"✅ Đã xoay camera hướng {ptz_direction.upper()} thành công.")
        else:
            print("⚠️ Không thể xoay camera.")

    # 4. Kiểm tra xem có phải yêu cầu chụp và lưu ảnh không
    want_save_photo = is_explicit_capture_request(prompt)

    need_new_snapshot, reuse_previous = determine_vision_mode(prompt, memory)
    if ptz_direction or want_save_photo:
        need_new_snapshot = True
        reuse_previous = False

    image_bytes = None
    saved_file_path = None

    if need_new_snapshot:
        print("📸 [Camera] Đang chụp frame mới từ camera...")
        try:
            image_bytes = capture_latest_frame()
            # Nếu người dùng yêu cầu chụp ảnh hoặc lưu ảnh, tự động lưu file vào folder data/captures
            if want_save_photo:
                saved_file_path = save_snapshot_to_disk(image_bytes)
                print(f"💾 [Lưu ảnh] Đã lưu file ảnh vào: {saved_file_path}")
        except CameraConnectionError as cam_err:
            print(f"⚠️  [Camera] Không chụp được ảnh ({cam_err}). Chuyển sang trả lời thuần text.")
            image_bytes = None
    elif reuse_previous:
        print("🔄 [Ngữ cảnh] Dùng lại hình ảnh gần nhất để trả lời tiếp nối...")

    # Nếu người dùng yêu cầu chụp ảnh, bổ sung chỉ dẫn ngữ cảnh cho Gemini
    actual_prompt = prompt
    if want_save_photo and saved_file_path:
        actual_prompt = f"{prompt} (Hệ thống đã chụp và lưu bức ảnh thành công vào {saved_file_path}. Hãy xác nhận em đã chụp và lưu ảnh vào máy cho anh, rồi mô tả ngắn gọn 1 câu những gì em thấy nhé.)"

    print("⏳ Bủn đang suy nghĩ...")
    reply = assistant.ask(
        prompt=actual_prompt,
        image_bytes=image_bytes,
        memory=memory,
        reuse_last_image=reuse_previous,
    )

    print(f"\n💬 Bủn: {reply}\n")

    # Phát giọng nói trả lời: Ưu tiên phát ra Loa của Camera Tiandy
    if enable_voice:
        success = play_on_camera_speaker(reply)
        if not success:
            print("🔊 [Loa PC] Phát qua loa máy tính...")
            speak_text(reply)

    return reply


def start_chat_mode(
    assistant: GeminiVisionAssistant,
    memory: ConversationMemory,
    enable_voice: bool = True,
) -> None:
    """Chế độ Chat văn bản chuyên dụng (Text Chat Mode)."""
    print("\n" + "=" * 64)
    print("💬  CHẾ ĐỘ CHAT VĂN BẢN VỚI TRỢ LÝ BỦN (TEXT CHAT)")
    print("=" * 64)
    print(" • Hãy nhập câu hỏi bằng bàn phím để trò chuyện.")
    print(" • Thử: 'chụp ảnh', 'chụp lại một tấm', 'nhìn sang trái', 'nói to lên'...")
    print(" • Gõ /back để quay lại menu chính.\n")

    while True:
        try:
            user_msg = input("✍️  Chat: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n🔙 Thoát chế độ chat văn bản.\n")
            break

        if not user_msg:
            continue

        if user_msg.lower() in ["/back", "back", "exit", "quit", "q"]:
            print("🔙 Đã quay về menu chính.\n")
            break

        if user_msg.lower() == "/clear":
            memory.clear()
            print("🧹 Đã xóa lịch sử trò chuyện.\n")
            continue

        try:
            process_query_and_reply(user_msg, assistant, memory, enable_voice=enable_voice)
        except GeminiServiceError as ai_err:
            print(f"❌ [Lỗi AI] {ai_err}\n")
        except Exception as exc:
            print(f"❌ [Lỗi] {exc}\n")


def start_voice_mode(assistant: GeminiVisionAssistant, memory: ConversationMemory) -> None:
    """Chế độ tự động lắng nghe liên tục từ Microphone Camera Tiandy."""
    print("\n" + "=" * 64)
    print("🎙️  CHẾ ĐỘ TỰ ĐỘNG NGHE LIÊN TỤC TỪ MIC CAMERA TIANDY")
    print("=" * 64)
    print(" • Bủn đang lắng nghe âm thanh từ camera phòng bạn.")
    print(" • Hãy đứng gần camera và nói rõ ràng (ví dụ: 'chụp ảnh', 'nhìn sang trái').")
    print(" • Nhấn Ctrl + C để dừng chế độ này và quay lại menu.\n")

    listener = CameraAudioListener()
    try:
        for recognized_text in listener.listen_phrases():
            print(f"👤 Bạn (từ Mic Camera): \"{recognized_text}\"")
            try:
                process_query_and_reply(recognized_text, assistant, memory, enable_voice=True)
            except GeminiServiceError as ai_err:
                print(f"❌ [Lỗi AI] {ai_err}\n")
            except Exception as exc:
                print(f"❌ [Lỗi] {exc}\n")

    except KeyboardInterrupt:
        print("\n🛑 Đã dừng chế độ nghe liên tục. Quay lại menu.\n")
    except CameraAudioError as audio_err:
        print(f"\n❌ [Lỗi Mic Camera] {audio_err}\n")
    finally:
        listener.stop()


def print_banner() -> None:
    """In giao diện chào mừng và hướng dẫn."""
    cur_vol = volume_controller.get_volume()
    print("=" * 64)
    print("         🤖 BUN CAMERA AI - TRỢ LÝ QUAN SÁT THÔNG MINH")
    print("=" * 64)
    print(f" • Model AI     : {settings.GEMINI_MODEL}")
    print(f" • Camera RTSP  : {settings.CAMERA_RTSP_URL}")
    print(f" • Âm lượng Loa : {cur_vol}%")
    print(" • Tính năng nổi bật:")
    print("     /snap      : Chụp và lưu ảnh vào folder data/captures/ 💾")
    print("     /chat      : Vào chế độ Chat văn bản chuyên dụng")
    print("     /dance     : Bủn biểu diễn màn nhảy múa lắc lư camera 💃")
    print("     /vol <1-100>: Chỉnh âm lượng loa camera (vd: /vol 80, /vol +, /vol -)")
    print("     /mic       : Nói 1 câu qua Mic Laptop/PC (chất lượng HD)")
    print("     /voice     : Chế độ tự động nghe liên tục từ Mic Camera")
    print("     /left, /right, /up, /down : Lệnh xoay camera nhanh")
    print("     /mute      : Bật/tắt phát giọng nói qua loa")
    print("     exit       : Thoát chương trình (hoặc q)")
    print("-" * 64)


def handle_volume_command(cmd_text: str) -> None:
    """Xử lý lệnh điều khiển âm lượng từ terminal."""
    parts = cmd_text.strip().split()
    if len(parts) == 1:
        cur = volume_controller.get_volume()
        print(f"🔊 [Âm lượng] Mức âm lượng loa camera hiện tại: {cur}%\n")
        return

    arg = parts[1].lower()
    if arg in ["+", "up", "tang", "tăng"]:
        new_val = volume_controller.increase_volume(20)
    elif arg in ["-", "down", "giam", "giảm"]:
        new_val = volume_controller.decrease_volume(20)
    else:
        try:
            target = int(arg)
            new_val = volume_controller.set_volume(target)
        except ValueError:
            print("⚠️ Cú pháp âm lượng không đúng. Ví dụ: /vol 80, /vol +, /vol -\n")
            return

    print(f"🔊 [Âm lượng] Đã chỉnh âm lượng loa camera thành: {new_val}%\n")


def handle_snap_and_save(assistant: GeminiVisionAssistant, memory: ConversationMemory, voice_enabled: bool) -> None:
    """Chụp frame camera, lưu vào thư mục data/captures và nhờ Bủn mô tả."""
    print("\n📸 [Camera] Đang chụp frame mới nhất từ camera...")
    try:
        image_bytes = capture_latest_frame()
        file_path = save_snapshot_to_disk(image_bytes)
        print(f"💾 [Lưu ảnh] Đã lưu thành công bức ảnh vào: {file_path}")
        print("🔍 [Bủn] Đang quan sát khung cảnh...")
        prompt = "Em vừa chụp một bức ảnh và lưu vào máy cho anh. Hãy xác nhận đã chụp và lưu ảnh thành công, rồi mô tả ngắn gọn 1-2 câu những gì em nhìn thấy nhé."
        reply = assistant.ask(
            prompt=prompt,
            image_bytes=image_bytes,
            memory=memory,
        )
        print(f"\n💬 Bủn: {reply}\n")
        if voice_enabled:
            if not play_on_camera_speaker(reply):
                speak_text(reply)
    except Exception as exc:
        print(f"❌ [Lỗi] {exc}\n")


def main() -> None:
    """Hàm khởi chạy ứng dụng chính."""
    volume_controller.set_volume(90)
    print_banner()

    config_errors = settings.validate()
    if config_errors:
        print("⚠️  PHÁT HIỆN LỖI CẤU HÌNH:")
        for err in config_errors:
            print(f"   - {err}")
        sys.exit(1)

    try:
        assistant = GeminiVisionAssistant()
        memory = ConversationMemory()
        voice_enabled = True
        print("✅ Đã sẵn sàng kết nối cùng trợ lý Bủn!\n")
    except Exception as exc:
        print(f"❌ Lỗi khởi tạo: {exc}")
        sys.exit(1)

    while True:
        try:
            user_input = input("👉 Lệnh (/chat, /snap, /dance, /vol, /mic, exit): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Bủn chào bạn nhé! Hẹn gặp lại.")
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ["exit", "quit", "q"]:
            print("👋 Bủn chào bạn nhé!")
            break

        # Lệnh chụp và lưu ảnh
        if cmd == "/snap":
            handle_snap_and_save(assistant, memory, voice_enabled)
            continue

        # Lệnh nhảy múa
        if cmd in ["/dance", "/nhay", "/mua", "/nhay-mua"]:
            perform_dance(enable_voice=voice_enabled)
            continue

        # Lệnh âm lượng
        if cmd.startswith("/vol") or cmd.startswith("/volume"):
            handle_volume_command(user_input)
            continue

        # Lệnh điều khiển xoay camera trực tiếp
        if cmd in ["/left", "/quay-trai"]:
            ptz_controller.move("left", duration=1.0)
            print("🔄 [PTZ] Đã quay camera sang trái.\n")
            continue

        if cmd in ["/right", "/quay-phai"]:
            ptz_controller.move("right", duration=1.0)
            print("🔄 [PTZ] Đã quay camera sang phải.\n")
            continue

        if cmd in ["/up", "/nguoc-len"]:
            ptz_controller.move("up", duration=0.8)
            print("🔄 [PTZ] Đã ngước camera lên.\n")
            continue

        if cmd in ["/down", "/cui-xuong"]:
            ptz_controller.move("down", duration=0.8)
            print("🔄 [PTZ] Đã cúi camera xuống.\n")
            continue

        if cmd == "/chat":
            start_chat_mode(assistant, memory, enable_voice=voice_enabled)
            continue

        if cmd.startswith("/chat "):
            msg = user_input[6:].strip()
            if msg:
                process_query_and_reply(msg, assistant, memory, enable_voice=voice_enabled)
            continue

        if cmd == "/voice":
            start_voice_mode(assistant, memory)
            continue

        if cmd == "/mic":
            query = listen_from_pc_mic()
            if query:
                print(f"👤 Bạn (Mic PC): \"{query}\"")
                process_query_and_reply(query, assistant, memory, enable_voice=voice_enabled)
            continue

        if cmd == "/mute":
            voice_enabled = not voice_enabled
            state = "BẬT" if voice_enabled else "TẮT"
            print(f"🔊 [Âm thanh] Đã {state} giọng nói của Bủn.\n")
            continue

        if cmd == "/clear":
            memory.clear()
            print("🧹 [Hệ thống] Đã xóa toàn bộ lịch sử trò chuyện và ảnh.\n")
            continue

        if cmd == "/help":
            print_banner()
            continue

        # Xử lý câu hỏi/câu nói trực tiếp
        try:
            process_query_and_reply(user_input, assistant, memory, enable_voice=voice_enabled)
        except GeminiServiceError as ai_err:
            print(f"\n❌ [Lỗi AI] {ai_err}\n")
        except Exception as exc:
            print(f"\n❌ [Lỗi không xác định] {exc}\n")


if __name__ == "__main__":
    main()
