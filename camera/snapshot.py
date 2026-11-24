"""Kết nối RTSP qua OpenCV/FFmpeg và chụp/lưu frame từ camera IP."""

from datetime import datetime
import logging
import os
from pathlib import Path
from typing import Optional, Tuple
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
    """Kết nối tới camera IP qua luồng RTSP và chụp frame mới nhất dạng bytes trong RAM."""
    url = rtsp_url or settings.CAMERA_RTSP_URL
    if not url:
        raise CameraConnectionError(
            "Chưa cấu hình CAMERA_RTSP_URL. Vui lòng kiểm tra file .env"
        )

    target_max_width = max_width or settings.MAX_IMAGE_WIDTH
    target_quality = jpeg_quality or settings.JPEG_QUALITY

    # Bắt buộc sử dụng TCP cho luồng RTSP trên OpenCV FFmpeg backend để tránh vỡ hình
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

    cap = None
    try:
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            raise CameraConnectionError(
                "Không thể mở luồng RTSP camera. Hãy kiểm tra địa chỉ IP, tài khoản/mật khẩu và kết nối mạng."
            )

        # Xả bỏ các frame cũ trong buffer
        for _ in range(flush_frames):
            if not cap.grab():
                break

        # Đọc frame mới nhất
        success, frame = cap.read()
        if not success or frame is None:
            raise CameraConnectionError(
                "Đã kết nối camera nhưng không đọc được frame hình ảnh từ luồng RTSP."
            )

        # Resize chiều ngang tối đa 1280px giữ nguyên tỷ lệ
        height, width = frame.shape[:2]
        if width > target_max_width:
            scale = target_max_width / float(width)
            new_width = target_max_width
            new_height = int(height * scale)
            frame = cv2.resize(
                frame, (new_width, new_height), interpolation=cv2.INTER_AREA
            )

        # Nén sang JPEG bytes trong RAM
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
        if cap is not None and cap.isOpened():
            cap.release()


def save_snapshot_to_disk(
    image_bytes: bytes,
    subfolder: str = "captures",
) -> str:
    """Lưu dữ liệu ảnh bytes thành file ảnh .jpg trong thư mục data của dự án.

    Args:
        image_bytes: Dữ liệu ảnh JPEG bytes.
        subfolder: Tên thư mục con trong data/ (mặc định: 'captures').

    Returns:
        str: Đường dẫn tương đối của file ảnh vừa lưu.
    """
    base_dir = Path(__file__).resolve().parent.parent
    save_dir = base_dir / "data" / subfolder
    save_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"snapshot_{timestamp_str}.jpg"
    file_path = save_dir / filename

    with open(file_path, "wb") as f:
        f.write(image_bytes)

    rel_path = f"data/{subfolder}/{filename}"
    logger.info("Đã lưu ảnh chụp camera: %s", rel_path)
    return rel_path
