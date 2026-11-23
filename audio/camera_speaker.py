"""Đẩy luồng âm thanh trực tiếp vào Loa ngoài của Camera Tiandy qua chuẩn ONVIF RTSP Backchannel."""

import asyncio
import hashlib
import io
import logging
import os
import re
import socket
import struct
import subprocess
import sys
import time
from urllib.parse import urlparse

import av
import edge_tts
import numpy as np

from camera.volume import volume_controller
from config.settings import settings

logger = logging.getLogger(__name__)


def generate_mp3_safely(text: str, output_path: str, voice: str = "vi-VN-HoaiMyNeural") -> bool:
    """Sinh file MP3 an toàn, ưu tiên edge-tts CLI để tránh xung đột event loop."""
    edge_tts_cli = os.path.join(os.path.dirname(sys.executable), "edge-tts.exe")
    if os.path.exists(edge_tts_cli):
        try:
            cmd = [edge_tts_cli, "--voice", voice, "--text", text, "--write-media", output_path]
            res = subprocess.run(cmd, capture_output=True, timeout=12)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
        except Exception as e:
            logger.debug("Edge-TTS CLI error: %s, chuyển sang fallback SDK", e)

    try:
        async def _save():
            comm = edge_tts.Communicate(text, voice)
            await comm.save(output_path)

        asyncio.run(_save())
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as exc:
        logger.error("Lỗi tạo âm thanh Edge-TTS: %s", exc)
        return False


def generate_pcma_audio(text: str, voice: str = "vi-VN-HoaiMyNeural") -> bytes:
    """Tạo âm thanh từ Edge-TTS, áp dụng Digital Volume Gain trực tiếp và nén PCMA 8000Hz Mono."""
    temp_mp3 = f"temp_tts_{os.getpid()}_{int(time.time()*1000)}.mp3"

    try:
        success = generate_mp3_safely(text, temp_mp3, voice)
        if not success:
            return b""

        inp = av.open(temp_mp3)
        out_io = io.BytesIO()
        out = av.open(out_io, mode="w", format="alaw")
        out_stream = out.add_stream("pcm_alaw", rate=8000, layout="mono")

        resampler = av.AudioResampler(format="s16", layout="mono", rate=8000)

        # Tính toán hệ số khuếch đại âm lượng Digital Gain (từ 0.05 đến 1.4)
        vol_pct = volume_controller.get_volume()
        gain = (vol_pct / 100.0) * 1.25

        for frame in inp.decode(audio=0):
            for r_frame in resampler.resample(frame):
                # Lấy mảng PCM 16-bit
                pcm_arr = r_frame.to_ndarray()

                # Nhân hệ số âm lượng và clip chống méo tiếng
                scaled_pcm = np.clip(pcm_arr.astype(np.float32) * gain, -32768, 32767).astype(np.int16)

                # Tạo AudioFrame mới với âm lượng đã được điều chỉnh
                scaled_frame = av.AudioFrame.from_ndarray(scaled_pcm, format="s16", layout="mono")
                scaled_frame.rate = 8000

                for packet in out_stream.encode(scaled_frame):
                    out.mux(packet)

        for packet in out_stream.encode(None):
            out.mux(packet)

        out.close()
        inp.close()
        return out_io.getvalue()

    except Exception as exc:
        logger.error("Lỗi encode PCMA: %s", exc)
        return b""
    finally:
        if os.path.exists(temp_mp3):
            try:
                os.remove(temp_mp3)
            except Exception:
                pass


def build_rtp_packet(payload: bytes, seq: int, timestamp: int, ssrc: int = 0x37CDA0A0, pt: int = 8) -> bytes:
    """Đóng gói payload âm thanh thành gói tin chuẩn RTP (Payload Type 8 = PCMA)."""
    header = struct.pack("!BBHII", 0x80, pt, seq & 0xFFFF, timestamp & 0xFFFFFFFF, ssrc)
    return header + payload


def play_on_camera_speaker(text: str, rtsp_url: str = None) -> bool:
    """Phát trực tiếp âm thanh giọng nói qua Loa của Camera Tiandy qua RTSP Backchannel."""
    raw_url = rtsp_url or settings.CAMERA_RTSP_URL
    if not raw_url:
        return False

    parsed = urlparse(raw_url)
    ip = parsed.hostname or "192.168.0.101"
    port = parsed.port or 554
    user = parsed.username or "Admin"
    pwd = parsed.password or ""
    path = parsed.path or "/1/1"

    base_url = f"rtsp://{ip}:{port}{path}"
    track_url = f"{base_url}/trackID=3"

    try:
        # 1. Chuyển đổi giọng nói sang định dạng PCMA 8000Hz với âm lượng đã điều chỉnh
        pcma_data = generate_pcma_audio(text)
        if not pcma_data:
            return False

        # 2. Mở kết nối TCP tới RTSP server của camera
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(6.0)
        s.connect((ip, port))

        cseq = 1

        def send_rtsp_req(cmd: str, url: str, extra_headers: str = "", auth_hdr: str = "") -> str:
            nonlocal cseq
            req = f"{cmd} {url} RTSP/1.0\r\nCSeq: {cseq}\r\n"
            if auth_hdr:
                req += f"Authorization: {auth_hdr}\r\n"
            if extra_headers:
                req += f"{extra_headers}\r\n"
            req += "\r\n"
            s.sendall(req.encode())
            res = s.recv(4096).decode("utf-8", errors="ignore")
            cseq += 1
            return res

        # Gửi DESCRIBE lấy digest nonce
        res_desc1 = send_rtsp_req(
            "DESCRIBE",
            base_url,
            "Require: www.onvif.org/ver20/backchannel\r\nAccept: application/sdp",
        )

        realm = res_desc1.split('realm="')[1].split('"')[0] if 'realm="' in res_desc1 else "RTSP SERVER"
        nonce = res_desc1.split('nonce="')[1].split('"')[0] if 'nonce="' in res_desc1 else ""

        def calc_auth(cmd: str, url: str) -> str:
            ha1 = hashlib.md5(f"{user}:{realm}:{pwd}".encode()).hexdigest()
            ha2 = hashlib.md5(f"{cmd}:{url}".encode()).hexdigest()
            resp = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
            return f'Digest username="{user}", realm="{realm}", nonce="{nonce}", uri="{url}", response="{resp}"'

        # Gửi DESCRIBE có xác thực
        send_rtsp_req(
            "DESCRIBE",
            base_url,
            "Require: www.onvif.org/ver20/backchannel\r\nAccept: application/sdp",
            calc_auth("DESCRIBE", base_url),
        )

        # Gửi SETUP thiết lập kênh Backchannel trên trackID=3 (TCP Interleaved 4-5)
        res_setup = send_rtsp_req(
            "SETUP",
            track_url,
            "Require: www.onvif.org/ver20/backchannel\r\nTransport: RTP/AVP/TCP;unicast;interleaved=4-5",
            calc_auth("SETUP", track_url),
        )

        session = ""
        rtp_channel = 4
        ssrc_val = 0x37CDA0A0

        for line in res_setup.splitlines():
            line_clean = line.strip()
            if line_clean.lower().startswith("session:"):
                session = line_clean.split(":")[1].split(";")[0].strip()
            if "interleaved=" in line_clean.lower():
                match = re.search(r"interleaved=(\d+)-(\d+)", line_clean, re.IGNORECASE)
                if match:
                    rtp_channel = int(match.group(1))
            if "ssrc=" in line_clean.lower():
                match_ssrc = re.search(r"ssrc=([0-9a-fA-F]+)", line_clean)
                if match_ssrc:
                    try:
                        ssrc_val = int(match_ssrc.group(1), 16)
                    except Exception:
                        pass

        if not session:
            s.close()
            return False

        # Gửi PLAY kích hoạt loa phát âm thanh
        send_rtsp_req("PLAY", base_url, f"Session: {session}", calc_auth("PLAY", base_url))

        # 3. Đẩy các gói tin RTP PCMA vào Kênh Interleaved của Camera
        chunk_size = 320  # 320 bytes = 40ms ở 8000Hz
        seq = 1
        timestamp = 0
        t_step = 320

        cur_vol = volume_controller.get_volume()
        print(f"📢 [Loa Camera] Đang phát tiếng nói ra loa Camera Tiandy (Âm lượng: {cur_vol}%)...")

        for offset in range(0, len(pcma_data), chunk_size):
            chunk = pcma_data[offset : offset + chunk_size]
            if not chunk:
                break
            rtp = build_rtp_packet(chunk, seq, timestamp, ssrc=ssrc_val, pt=8)
            interleaved_header = struct.pack("!BBH", 0x24, rtp_channel, len(rtp))
            s.sendall(interleaved_header + rtp)
            seq += 1
            timestamp += t_step
            time.sleep(0.038)

        # Đợi camera phát xong buffer âm thanh
        time.sleep(0.4)

        # Gửi TEARDOWN đóng phiên đàm thoại
        send_rtsp_req("TEARDOWN", base_url, f"Session: {session}", calc_auth("TEARDOWN", base_url))
        s.close()
        return True

    except Exception as exc:
        logger.warning("Không thể phát qua loa camera Tiandy: %s", exc)
        return False
