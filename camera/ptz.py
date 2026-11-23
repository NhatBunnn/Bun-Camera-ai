"""Điều khiển xoay camera PTZ (Pan/Tilt/Zoom) qua chuẩn ONVIF."""

import logging
import time
from typing import Optional
from urllib.parse import urlparse

from onvif import ONVIFCamera
from config.settings import settings

logger = logging.getLogger(__name__)


class PTZController:
    """Lớp điều khiển xoay camera Tiandy PTZ:

    - Xoay trái, phải, lên, xuống theo thời gian hoặc bước di chuyển.
    - Tính năng vũ đạo nhảy múa (PTZ Dance) lắc lư vui nhộn.
    """

    def __init__(self, rtsp_url: Optional[str] = None):
        raw_url = rtsp_url or settings.CAMERA_RTSP_URL
        parsed = urlparse(raw_url)
        self.ip = parsed.hostname or "192.168.0.101"
        self.port = 80  # ONVIF Port
        self.user = parsed.username or "Admin"
        self.pwd = parsed.password or ""
        self._cam = None
        self._ptz = None
        self._profile_token = None

    def _connect(self):
        """Khởi tạo kết nối ONVIF PTZ nếu chưa kết nối."""
        if self._ptz is None:
            self._cam = ONVIFCamera(self.ip, self.port, self.user, self.pwd)
            self._ptz = self._cam.create_ptz_service()
            media = self._cam.create_media_service()
            profiles = media.GetProfiles()
            if not profiles:
                raise RuntimeError("Không tìm thấy ONVIF profile trên camera.")
            self._profile_token = profiles[0].token

    def move(self, direction: str, duration: float = 1.0, speed: float = 0.55) -> bool:
        """Xoay camera theo hướng chỉ định."""
        try:
            self._connect()
        except Exception as exc:
            logger.error("Lỗi kết nối PTZ: %s", exc)
            return False

        d = direction.lower().strip()
        vx, vy = 0.0, 0.0

        if any(k in d for k in ["trái", "trai", "left"]):
            vx = -speed
        elif any(k in d for k in ["phải", "phai", "right"]):
            vx = speed

        if any(k in d for k in ["lên", "len", "trên", "tren", "up"]):
            vy = speed
        elif any(k in d for k in ["xuống", "xuong", "dưới", "duoi", "down"]):
            vy = -speed

        if vx == 0.0 and vy == 0.0:
            return False

        try:
            req = {
                "ProfileToken": self._profile_token,
                "Velocity": {
                    "PanTilt": {"x": vx, "y": vy}
                },
            }
            self._ptz.ContinuousMove(req)
            time.sleep(duration)
            self._ptz.Stop({"ProfileToken": self._profile_token})
            time.sleep(0.4)
            return True
        except Exception as exc:
            logger.error("Lỗi gửi lệnh PTZ: %s", exc)
            try:
                self._ptz.Stop({"ProfileToken": self._profile_token})
            except Exception:
                pass
            return False

    def dance(self, speed: float = 0.6) -> bool:
        """Thực hiện một điệu nhảy lắc lư nhịp nhàng bằng động cơ camera PTZ."""
        try:
            self._connect()
        except Exception as exc:
            logger.error("Lỗi kết nối PTZ khi nhảy múa: %s", exc)
            return False

        moves = [
            (-speed, 0.0, 0.35),   # Lắc sang trái
            (speed, 0.0, 0.7),     # Lắc mạnh sang phải
            (-speed, 0.0, 0.7),    # Lắc mạnh sang trái
            (speed, 0.0, 0.35),    # Về giữa
            (0.0, speed * 0.7, 0.3),  # Ngước đầu lên vui vẻ
            (0.0, -speed * 0.7, 0.5), # Cúi đầu nhún nhảy
            (0.0, speed * 0.7, 0.2),  # Cân bằng lại
            (-speed * 0.8, 0.0, 0.3), # Lắc nhẹ kết bài
            (speed * 0.8, 0.0, 0.3),
        ]

        try:
            for vx, vy, duration in moves:
                req = {
                    "ProfileToken": self._profile_token,
                    "Velocity": {
                        "PanTilt": {"x": vx, "y": vy}
                    },
                }
                self._ptz.ContinuousMove(req)
                time.sleep(duration)
            self._ptz.Stop({"ProfileToken": self._profile_token})
            time.sleep(0.3)
            return True
        except Exception as exc:
            logger.error("Lỗi trong lúc nhảy múa: %s", exc)
            try:
                self._ptz.Stop({"ProfileToken": self._profile_token})
            except Exception:
                pass
            return False

    def stop(self) -> None:
        """Dừng mọi chuyển động xoay."""
        try:
            self._connect()
            self._ptz.Stop({"ProfileToken": self._profile_token})
        except Exception:
            pass


ptz_controller = PTZController()
