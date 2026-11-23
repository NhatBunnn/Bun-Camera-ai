"""Kết nối RTSP qua OpenCV/FFmpeg và chụp frame mới nhất từ camera IP."""

import logging
import os
from typing import Optional
import cv2

from config.settings import settings

logger = logging.getLogger(__name__)


class CameraConnectionError(Exception):
    """Ngoại lệ khi không thể kết nối hoặc đọc frame từ camera RTSP."""

    pass


def capture_latest_frame(
    rtsp_url: Optional[str] = None,
    max_width: Optional[int] = None,
    jpeg_quality: Optional[int] = None,
    flush_frames: int = 5,
) -> bytes:
    """Kết nối tới camera IP qua luồng RTSP và chụp frame mới nhất.

    Quy trình xử lý:
    1. Thiết lập giao thức TCP cho FFmpeg để chống vỡ hình/mất gói RTSP (đặc biệt camera Tiandy).
    2. Mở kết nối VideoCapture với backend FFMPEG.
    3. Xả bỏ các frame cũ đang tồn đọng trong buffer nội bộ (cap.grab()).
    4. Đọc frame hiện tại (cap.read()).
    5. Resize giữ nguyên tỷ lệ khung hình nếu chiều ngang vượt quá max_width.
    6. Nén thành chuẩn JPEG bytes (in-memory) để gửi trực tiếp cho Gemini API.
    7. Đảm bảo luôn giải phóng tài nguyên (cap.release()) trong khối finally.

    Args:
        rtsp_url: Đường dẫn RTSP của camera. Nếu None, lấy từ cấu hình settings.
        max_width: Chiều ngang tối đa (px). Nếu None, lấy từ settings.MAX_IMAGE_WIDTH (1280).
        jpeg_quality: Chất lượng nén ảnh JPEG (1-100). Mặc định lấy từ settings.JPEG_QUALITY (85).
        flush_frames: Số frame cần xả bỏ để tránh độ trễ (mặc định: 5).

    Returns:
        bytes: Dữ liệu ảnh nén JPEG dạng bytes trong bộ nhớ RAM.

    Raises:
        CameraConnectionError: Khi URL không hợp lệ, không kết nối được camera hoặc không đọc được frame.
    """
    url = rtsp_url or settings.CAMERA_RTSP_URL
    if not url:
        raise CameraConnectionError(
            "Chưa cấu hình CAMERA_RTSP_URL. Vui lòng kiểm tra file .env"
        )

    target_max_width = max_width or settings.MAX_IMAGE_WIDTH
    target_quality = jpeg_quality or settings.JPEG_QUALITY

    # Bắt buộc sử dụng TCP cho luồng RTSP trên OpenCV FFmpeg backend để tránh vỡ hình/mất gói H.264
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

    cap = None
    try:
        # Khởi tạo kết nối RTSP với FFMPEG backend
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

        # Giảm kích thước buffer nội bộ của OpenCV xuống 1 frame nếu backend hỗ trợ
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            raise CameraConnectionError(
                f"Không thể mở luồng RTSP camera. Hãy kiểm tra địa chỉ IP, tài khoản/mật khẩu và kết nối mạng."
            )

        # Xả bỏ các frame cũ trong hàng đợi buffer để lấy frame thời gian thực
        for _ in range(flush_frames):
            if not cap.grab():
                break

        # Đọc frame mới nhất
        success, frame = cap.read()
        if not success or frame is None:
            raise CameraConnectionError(
                "Đã kết nối camera nhưng không đọc được frame hình ảnh từ luồng RTSP."
            )

        # Xử lý resize chiều ngang tối đa 1280px giữ nguyên tỷ lệ
        height, width = frame.shape[:2]
        if width > target_max_width:
            scale = target_max_width / float(width)
            new_width = target_max_width
            new_height = int(height * scale)
            frame = cv2.resize(
                frame, (new_width, new_height), interpolation=cv2.INTER_AREA
            )

        # Nén sang JPEG bytes trong RAM với quality mong muốn
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), target_quality]
        encode_success, buffer = cv2.imencode(".jpg", frame, encode_params)

        if not encode_success:
            raise CameraConnectionError("Lỗi khi nén frame thành dữ liệu JPEG bytes.")

        return buffer.tobytes()

    except CameraConnectionError:
        raise
    except Exception as exc:
        raise CameraConnectionError(
            f"Lỗi bất thường khi kết nối camera: {str(exc)}"
        ) from exc
    finally:
        # Luôn luôn giải phóng kết nối camera
        if cap is not None and cap.isOpened():
            cap.release()
