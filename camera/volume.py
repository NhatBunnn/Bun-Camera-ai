"""Điều khiển âm lượng loa ngoài của Camera Tiandy qua ONVIF và khuếch đại kỹ thuật số."""

import logging
from typing import Optional
from urllib.parse import urlparse

from onvif import ONVIFCamera
from config.settings import settings

logger = logging.getLogger(__name__)


class CameraVolumeController:
    """Quản lý và điều chỉnh mức âm lượng loa của camera Tiandy:

    - Điều khiển phần cứng ONVIF OutputLevel (1 - 100%).
    - Đồng bộ mức âm lượng cho bộ mã hóa âm thanh.
    """

    def __init__(self, rtsp_url: Optional[str] = None):
        raw_url = rtsp_url or settings.CAMERA_RTSP_URL
        parsed = urlparse(raw_url)
        self.ip = parsed.hostname or "192.168.0.101"
        self.port = 80
        self.user = parsed.username or "Admin"
        self.pwd = parsed.password or ""
        self._cam = None
        self._media = None
        self._current_volume: int = 90  # Mặc định 90% để to rõ

    def _connect(self):
        if self._media is None:
            self._cam = ONVIFCamera(self.ip, self.port, self.user, self.pwd)
            self._media = self._cam.create_media_service()

    def get_volume(self) -> int:
        """Lấy mức âm lượng hiện tại của loa camera (1 - 100)."""
        try:
            self._connect()
            configs = self._media.GetAudioOutputConfigurations()
            if configs:
                self._current_volume = int(configs[0].OutputLevel)
        except Exception as exc:
            logger.debug("Không thể đọc volume từ ONVIF: %s", exc)
        return self._current_volume

    def set_volume(self, level: int) -> int:
        """Thiết lập mức âm lượng loa camera (1 - 100%).

        Args:
            level: Mức âm lượng từ 1 đến 100.

        Returns:
            int: Mức âm lượng thực tế đã thiết lập.
        """
        target = max(5, min(100, int(level)))
        self._current_volume = target

        try:
            self._connect()
            configs = self._media.GetAudioOutputConfigurations()
            if configs:
                cfg = configs[0]
                cfg.OutputLevel = target
                self._media.SetAudioOutputConfiguration({
                    "Configuration": cfg,
                    "ForcePersistence": True,
                })
        except Exception as exc:
            logger.warning("Không thể set volume qua ONVIF: %s", exc)

        return self._current_volume

    def increase_volume(self, step: int = 20) -> int:
        """Tăng âm lượng thêm một khoảng."""
        current = self.get_volume()
        return self.set_volume(current + step)

    def decrease_volume(self, step: int = 20) -> int:
        """Giảm âm lượng đi một khoảng."""
        current = self.get_volume()
        return self.set_volume(current - step)


volume_controller = CameraVolumeController()
