"""Camera capture with auto-detection, auto-reconnect and frame sharing."""
from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
import threading
import time

import cv2
import numpy as np

from .config import settings
from .ffmpeg import ffmpeg_exe

log = logging.getLogger("camera")
IS_MAC = platform.system() == "Darwin"
BUILTIN_NAMES = ("facetime", "built-in", "integrated", "macbook", "imac", "studio display", "pro display")
SKIP_NAMES = ("capture screen", "desk view", "iphone", "ipad", "obs virtual", "virtual")


def _backend():
    if IS_MAC:
        return cv2.CAP_AVFOUNDATION
    if platform.system() == "Windows":
        return cv2.CAP_DSHOW
    return cv2.CAP_V4L2


def list_camera_names() -> list[dict]:
    """Return [{index, name}] using the OS device list where possible."""
    out: list[dict] = []
    if IS_MAC:
        try:
            p = subprocess.run(
                [ffmpeg_exe(), "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                capture_output=True, text=True, timeout=10,
            )
            txt = p.stderr
            video_part = txt.split("AVFoundation audio devices")[0]
            for m in re.finditer(r"\[(\d+)\]\s+(.+)", video_part):
                name = m.group(2).strip()
                if "capture screen" in name.lower():
                    continue
                out.append({"index": int(m.group(1)), "name": name})
        except Exception as e:
            log.warning("Could not list AVFoundation devices: %s", e)
    elif platform.system() == "Linux":
        for dev in sorted(os.listdir("/dev")) if os.path.isdir("/dev") else []:
            if dev.startswith("video") and dev[5:].isdigit():
                idx = int(dev[5:])
                name = f"/dev/{dev}"
                try:
                    with open(f"/sys/class/video4linux/{dev}/name") as f:
                        name = f.read().strip()
                except Exception:
                    pass
                out.append({"index": idx, "name": name})
    return out


def probe_cameras(max_index: int = 5) -> list[dict]:
    """List cameras that can actually be opened."""
    names = {c["index"]: c["name"] for c in list_camera_names()}
    found = []
    indices = sorted(names.keys()) if names else range(max_index)
    for i in indices:
        cap = cv2.VideoCapture(i, _backend())
        ok = cap.isOpened()
        w = h = 0
        if ok:
            ret, frame = cap.read()
            ok = bool(ret)
            if ok:
                h, w = frame.shape[:2]
        cap.release()
        if ok:
            found.append({"index": i, "name": names.get(i, f"Camera {i}"), "width": w, "height": h})
    return found


def choose_auto_index() -> int:
    """Prefer an external USB webcam over built-in/virtual cameras."""
    cams = list_camera_names()
    if cams:
        external = [c for c in cams if not any(s in c["name"].lower() for s in SKIP_NAMES + BUILTIN_NAMES)]
        if external:
            log.info("Auto-selected external camera: [%s] %s", external[0]["index"], external[0]["name"])
            return external[0]["index"]
        usable = [c for c in cams if not any(s in c["name"].lower() for s in SKIP_NAMES)]
        if usable:
            log.warning("No USB webcam found — using built-in camera: [%s] %s", usable[0]["index"], usable[0]["name"])
            return usable[0]["index"]
    return 0


class Camera:
    def __init__(self):
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_ts = 0.0
        self._frame_seq = 0
        self._stop = threading.Event()
        self._restart = threading.Event()
        self._thread: threading.Thread | None = None
        self.connected = False
        self.source_desc = ""
        self.active_index: int | None = None
        self.fps = 0.0
        self.width = 0
        self.height = 0
        self.last_error = ""
        self.on_disconnect = None
        self.on_connect = None
        self._was_connected = False

    def start(self):
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def restart(self):
        self._restart.set()

    def get_frame(self):
        with self._lock:
            if self._frame is None:
                return None, 0, 0.0
            return self._frame, self._frame_seq, self._frame_ts

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "source": self.source_desc,
            "index": self.active_index,
            "fps": round(self.fps, 1),
            "width": self.width,
            "height": self.height,
            "error": self.last_error,
            "paused": settings.get("recording.paused"),
        }

    # ---------- internals ----------
    def _open(self):
        cfg = settings.section("camera")
        src = str(cfg.get("source", "auto")).strip()
        is_file = False
        if src == "auto" or src == "":
            idx = choose_auto_index()
            cap = cv2.VideoCapture(idx, _backend())
            self.active_index = idx
            self.source_desc = f"Auto (index {idx})"
        elif src.isdigit():
            idx = int(src)
            cap = cv2.VideoCapture(idx, _backend())
            self.active_index = idx
            self.source_desc = f"Camera index {idx}"
        else:
            cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
            self.active_index = None
            self.source_desc = re.sub(r"//[^@/]+@", "//***@", src)  # hide credentials
            is_file = os.path.isfile(src)
        if not cap.isOpened():
            cap.release()
            return None, False
        if self.active_index is not None:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(cfg.get("width", 1280)))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(cfg.get("height", 720)))
            cap.set(cv2.CAP_PROP_FPS, int(cfg.get("fps", 30)))
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
        return cap, is_file

    def _transform(self, frame):
        cfg = settings.section("camera")
        if cfg.get("flip_horizontal"):
            frame = cv2.flip(frame, 1)
        rot = int(cfg.get("rotate", 0))
        if rot == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif rot == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif rot == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return frame

    def _set_disconnected(self, err: str):
        self.connected = False
        self.last_error = err
        if self._was_connected:
            self._was_connected = False
            log.error("Camera disconnected: %s", err)
            if self.on_disconnect:
                try:
                    self.on_disconnect(err)
                except Exception:
                    log.exception("on_disconnect failed")

    def _run(self):
        while not self._stop.is_set():
            if settings.get("recording.paused"):
                self.connected = False
                self.last_error = "Privacy pause active"
                with self._lock:
                    self._frame = None
                time.sleep(0.5)
                continue
            self._restart.clear()
            cap, is_file = self._open()
            if cap is None:
                self._set_disconnected(f"Unable to open camera source ({self.source_desc})")
                self._stop.wait(settings.get("camera.reconnect_seconds", 3))
                continue
            src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
            frame_interval = 1.0 / max(1.0, min(src_fps, 60)) if is_file else 0
            fails = 0
            t_last = time.time()
            count = 0
            log.info("Camera opened: %s", self.source_desc)
            while not self._stop.is_set() and not self._restart.is_set() and not settings.get("recording.paused"):
                t0 = time.time()
                ok, frame = cap.read()
                if not ok or frame is None:
                    if is_file:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    fails += 1
                    if fails > 30:
                        break
                    time.sleep(0.05)
                    continue
                fails = 0
                frame = self._transform(frame)
                with self._lock:
                    self._frame = frame
                    self._frame_seq += 1
                    self._frame_ts = time.time()
                self.height, self.width = frame.shape[:2]
                if not self.connected:
                    self.connected = True
                    self.last_error = ""
                    if not self._was_connected:
                        self._was_connected = True
                        log.info("Camera streaming %dx%d", self.width, self.height)
                        if self.on_connect:
                            try:
                                self.on_connect()
                            except Exception:
                                pass
                count += 1
                if time.time() - t_last >= 2:
                    self.fps = count / (time.time() - t_last)
                    count = 0
                    t_last = time.time()
                if frame_interval:
                    dt = frame_interval - (time.time() - t0)
                    if dt > 0:
                        time.sleep(dt)
            cap.release()
            if self._stop.is_set():
                break
            if self._restart.is_set() or settings.get("recording.paused"):
                self.connected = False
                continue
            self._set_disconnected("Camera stopped delivering frames")
            with self._lock:
                self._frame = None
            self._stop.wait(settings.get("camera.reconnect_seconds", 3))
        self.connected = False


camera = Camera()
