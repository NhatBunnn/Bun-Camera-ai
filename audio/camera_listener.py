"""Thu âm giọng nói trực tiếp từ Microphone camera IP qua luồng RTSP Audio bằng PyAV."""

import logging
import math
import struct
import time
from typing import Generator, Optional

import av
import speech_recognition as sr

from config.settings import settings

logger = logging.getLogger(__name__)


class CameraAudioError(Exception):
    """Ngoại lệ khi không thể kết nối hoặc đọc luồng âm thanh từ camera."""

    pass


class CameraAudioListener:
    """Lắng nghe âm thanh từ luồng RTSP của camera Tiandy với độ nhạy cao và lọc nhiễu."""

    def __init__(
        self,
        rtsp_url: Optional[str] = None,
        sample_rate: int = 16000,
        energy_threshold: float = 220.0,   # Giảm ngưỡng để bắt tiếng nhạy hơn khi đứng xa camera
        silence_timeout: float = 0.9,     # Giảm thời gian chờ im lặng để phản hồi nhanh hơn
        min_speech_duration: float = 0.4,
        max_speech_duration: float = 12.0,
    ):
        self.rtsp_url = rtsp_url or settings.CAMERA_RTSP_URL
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.silence_timeout = silence_timeout
        self.min_speech_duration = min_speech_duration
        self.max_speech_duration = max_speech_duration

        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 200
        self.recognizer.dynamic_energy_threshold = True
        self.is_running = False

    def calculate_rms(self, pcm_bytes: bytes) -> float:
        """Tính toán giá trị RMS đo mức năng lượng âm lượng."""
        if not pcm_bytes:
            return 0.0
        count = len(pcm_bytes) // 2
        if count == 0:
            return 0.0
        format_str = f"<{count}h"
        try:
            shorts = struct.unpack(format_str, pcm_bytes)
            sum_squares = sum(s * s for s in shorts)
            return math.sqrt(sum_squares / count)
        except Exception:
            return 0.0

    def listen_phrases(self) -> Generator[str, None, None]:
        """Vòng lặp lắng nghe liên tục với cơ chế Auto-Reconnect và nhường kênh đàm thoại."""
        self.is_running = True

        while self.is_running:
            container = None
            try:
                container = av.open(
                    self.rtsp_url,
                    options={
                        "rtsp_transport": "tcp",
                        "buffer_size": "1024000",
                        "stimeout": "6000000",
                    },
                )

                audio_stream = next((s for s in container.streams if s.type == "audio"), None)
                if not audio_stream:
                    raise CameraAudioError("Không tìm thấy luồng âm thanh trên camera Tiandy.")

                resampler = av.AudioResampler(format="s16", layout="mono", rate=self.sample_rate)

                is_speaking = False
                speech_buffer = bytearray()
                silence_start_time = None
                speech_start_time = None

                print("👂 [Mic Camera] Đang lắng nghe âm thanh từ camera...")

                for packet in container.demux(audio_stream):
                    if not self.is_running:
                        break

                    for frame in packet.decode():
                        resampled_frames = resampler.resample(frame)
                        for r_frame in resampled_frames:
                            pcm_bytes = bytes(r_frame.planes[0])
                            current_rms = self.calculate_rms(pcm_bytes)
                            current_time = time.time()

                            if not is_speaking:
                                if current_rms > self.energy_threshold:
                                    is_speaking = True
                                    speech_start_time = current_time
                                    silence_start_time = None
                                    speech_buffer.clear()
                                    speech_buffer.extend(pcm_bytes)
                                    print("🎙️  [Bủn] Đang nghe bạn nói...")
                            else:
                                speech_buffer.extend(pcm_bytes)
                                duration = current_time - speech_start_time

                                if current_rms < self.energy_threshold:
                                    if silence_start_time is None:
                                        silence_start_time = current_time
                                    elif (current_time - silence_start_time) >= self.silence_timeout:
                                        if duration >= self.min_speech_duration:
                                            print("⏳ Đang nhận diện câu nói...")
                                            recognized_text = self._transcribe_pcm(bytes(speech_buffer))
                                            if recognized_text:
                                                try:
                                                    container.close()
                                                    container = None
                                                except Exception:
                                                    pass
                                                yield recognized_text
                                                break
                                        is_speaking = False
                                        speech_buffer.clear()
                                        silence_start_time = None
                                else:
                                    silence_start_time = None

                                if duration >= self.max_speech_duration:
                                    recognized_text = self._transcribe_pcm(bytes(speech_buffer))
                                    if recognized_text:
                                        try:
                                            container.close()
                                            container = None
                                        except Exception:
                                            pass
                                        yield recognized_text
                                        break
                                    is_speaking = False
                                    speech_buffer.clear()
                                    silence_start_time = None

                    if container is None:
                        break

            except (av.FFmpegError, OSError):
                if not self.is_running:
                    break
                time.sleep(1.0)
                continue

            except Exception:
                if not self.is_running:
                    break
                time.sleep(1.0)
                continue

            finally:
                if container:
                    try:
                        container.close()
                    except Exception:
                        pass

    def _transcribe_pcm(self, pcm_data: bytes) -> Optional[str]:
        """Chuyển đổi dữ liệu PCM thô thành văn bản tiếng Việt qua SpeechRecognition."""
        if not pcm_data:
            return None

        try:
            audio_data = sr.AudioData(pcm_data, self.sample_rate, 2)
            text = self.recognizer.recognize_google(audio_data, language="vi-VN")
            return text.strip()
        except sr.UnknownValueError:
            return None
        except Exception as exc:
            logger.error("Lỗi STT: %s", exc)
            return None

    def stop(self) -> None:
        """Dừng lắng nghe luồng âm thanh."""
        self.is_running = False
