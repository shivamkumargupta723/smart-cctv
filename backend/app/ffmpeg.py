"""FFmpeg helpers: locate binary and write browser-playable H.264 MP4 files."""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger("ffmpeg")
_exe: str | None = None
_encoder: str | None = None


def ffmpeg_exe() -> str:
    global _exe
    if _exe:
        return _exe
    exe = shutil.which("ffmpeg")
    if not exe:
        for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
            if Path(p).exists():
                exe = p
                break
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            exe = "ffmpeg"
    _exe = exe
    return exe


def pick_encoder() -> str:
    """libx264 preferred; fallback to Apple VideoToolbox hardware encoder."""
    global _encoder
    if _encoder:
        return _encoder
    try:
        out = subprocess.run([ffmpeg_exe(), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        out = ""
    if "libx264" in out:
        _encoder = "libx264"
    elif "h264_videotoolbox" in out:
        _encoder = "h264_videotoolbox"
    else:
        _encoder = "mpeg4"
    log.info("Video encoder: %s (%s)", _encoder, ffmpeg_exe())
    return _encoder


class VideoWriter:
    """Pipes raw BGR frames into ffmpeg -> H.264 MP4 (faststart, yuv420p)."""

    def __init__(self, path: Path, width: int, height: int, fps: int, crf: int = 23):
        self.path = Path(path)
        self.width = width - (width % 2)
        self.height = height - (height % 2)
        self.fps = fps
        self.frames = 0
        self._lock = threading.Lock()
        self.error = ""
        enc = pick_encoder()
        cmd = [
            ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{self.width}x{self.height}", "-r", str(fps),
            "-i", "pipe:0", "-an",
        ]
        if enc == "libx264":
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf)]
        elif enc == "h264_videotoolbox":
            cmd += ["-c:v", "h264_videotoolbox", "-b:v", "4M"]
        else:
            cmd += ["-c:v", "mpeg4", "-q:v", "5"]
        cmd += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(self.path)]
        # own session: Ctrl+C in Terminal must not kill ffmpeg before the file is finalized
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)

    def write(self, frame: np.ndarray) -> bool:
        with self._lock:
            if self.proc.poll() is not None:
                return False
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))
            try:
                self.proc.stdin.write(np.ascontiguousarray(frame).tobytes())
                self.frames += 1
                return True
            except (BrokenPipeError, OSError) as e:
                self.error = str(e)
                return False

    def close(self) -> bool:
        with self._lock:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            err = self.proc.stderr.read().decode(errors="ignore") if self.proc.stderr else ""
            if self.proc.returncode != 0:
                self.error = err.strip()[-500:]
                log.error("ffmpeg failed for %s: %s", self.path.name, self.error)
                return False
            return self.path.exists() and self.path.stat().st_size > 0
