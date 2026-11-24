"""Module xử lý camera, snapshot, điều khiển xoay PTZ và âm lượng."""

from camera.snapshot import capture_latest_frame, save_snapshot_to_disk
from camera.ptz import ptz_controller, PTZController
from camera.volume import volume_controller, CameraVolumeController

__all__ = [
    "capture_latest_frame",
    "save_snapshot_to_disk",
    "ptz_controller",
    "PTZController",
    "volume_controller",
    "CameraVolumeController",
]
