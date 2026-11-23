"""Module xử lý âm thanh: Text-to-Speech, RTSP Camera Mic, PC Mic, và Loa Camera Tiandy."""

from audio.text_to_speech import speak_text
from audio.camera_listener import CameraAudioListener
from audio.camera_speaker import play_on_camera_speaker
from audio.pc_listener import listen_from_pc_mic

__all__ = ["speak_text", "CameraAudioListener", "play_on_camera_speaker", "listen_from_pc_mic"]
