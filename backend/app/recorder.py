"""Continuous (segmented) and event recording with pre-event buffer."""
from __future__ import annotations

import collections
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2

from .camera import camera
from .config import CONT_DIR, EVENT_DIR, settings
from .db import db
from .detector import annotate, stamp
from .ffmpeg import VideoWriter

log = logging.getLogger("recorder")


def _thumb(frame, video_path: Path) -> str:
    tp = video_path.with_suffix(".jpg")
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (480, int(480 * h / w)))
    cv2.imwrite(str(tp), small, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return str(tp)


class _Segment:
    def __init__(self, kind: str, path: Path, frame, fps: int, crf: int, event_id: int | None = None, thumb_frame=None):
        h, w = frame.shape[:2]
        self.writer = VideoWriter(path, w, h, fps, crf)
        self.path = path
        self.started = time.time()
        self.kind = kind
        self.rec_id = db.insert("recordings", {
            "kind": kind, "event_id": event_id, "path": str(path), "thumb_path": _thumb(thumb_frame if thumb_frame is not None else frame, path),
            "started_at": self.started, "status": "recording",
        })

    def write(self, frame) -> bool:
        return self.writer.write(frame)

    def close(self):
        fps = self.writer.fps
        ok = self.writer.close()
        size = self.path.stat().st_size if self.path.exists() else 0
        db.update("recordings", self.rec_id, {
            "ended_at": time.time(), "duration": round(self.writer.frames / max(fps, 1), 2),
            "size": size, "status": "complete" if ok and self.writer.frames > 0 else "failed",
        })
        if not ok or self.writer.frames == 0:
            log.warning("Recording %s failed or empty", self.path.name)
        else:
            log.info("Saved %s recording %s (%.1fs, %.1f MB)", self.kind, self.path.name, self.writer.frames / fps, size / 1e6)
        return self.rec_id


class Recorder:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self.continuous: _Segment | None = None
        self.event_seg: _Segment | None = None
        self.event_id: int | None = None
        self._event_stop_at: float | None = None
        self._buffer: collections.deque = collections.deque()
        self.latest_result = None  # set by engine for annotation

    def start(self):
        self._thread = threading.Thread(target=self._run, name="recorder", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        with self._lock:
            self._close_continuous()
            self._close_event()

    def status(self) -> dict:
        cfg = settings.section("recording")
        return {
            "paused": cfg.get("paused"),
            "continuous_enabled": cfg.get("continuous_enabled"),
            "event_enabled": cfg.get("event_enabled"),
            "continuous_active": self.continuous is not None,
            "event_active": self.event_seg is not None,
            "recording": self.continuous is not None or self.event_seg is not None,
            "continuous_file": self.continuous.path.name if self.continuous else None,
            "event_file": self.event_seg.path.name if self.event_seg else None,
        }

    # ---------- event control (called by engine) ----------
    def start_event(self, event_id: int, label: str) -> int | None:
        cfg = settings.section("recording")
        if cfg.get("paused") or not cfg.get("event_enabled", True):
            return None
        with self._lock:
            self._event_stop_at = None
            if self.event_seg is not None:
                return self.event_seg.rec_id
            frame, _, _ = camera.get_frame()
            if frame is None:
                return None
            name = datetime.now().strftime("event_%Y%m%d_%H%M%S") + f"_{label}.mp4"
            day = EVENT_DIR / datetime.now().strftime("%Y-%m-%d")
            day.mkdir(parents=True, exist_ok=True)
            fps = int(cfg.get("record_fps", 15))
            first = self._buffer[0][1] if self._buffer else frame
            self.event_seg = _Segment("event", day / name, first, fps, int(cfg.get("video_crf", 23)), event_id, thumb_frame=frame)
            self.event_id = event_id
            for _, f in list(self._buffer):  # pre-event footage
                self.event_seg.write(f)
            log.info("Event recording started: %s (pre-buffer %d frames)", name, len(self._buffer))
            return self.event_seg.rec_id

    def schedule_event_stop(self):
        with self._lock:
            if self.event_seg is not None and self._event_stop_at is None:
                self._event_stop_at = time.time() + float(settings.get("recording.post_event_seconds", 10))

    def cancel_event_stop(self):
        with self._lock:
            self._event_stop_at = None

    # ---------- internals ----------
    def _close_event(self):
        if self.event_seg is not None:
            seg, self.event_seg = self.event_seg, None
            seg.close()
            self.event_id = None
            self._event_stop_at = None

    def _close_continuous(self):
        if self.continuous is not None:
            seg, self.continuous = self.continuous, None
            seg.close()

    def _run(self):
        next_t = time.time()
        while not self._stop.is_set():
            cfg = settings.section("recording")
            fps = max(1, int(cfg.get("record_fps", 15)))
            interval = 1.0 / fps
            next_t += interval
            delay = next_t - time.time()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.time()
            try:
                self._tick(cfg, fps)
            except Exception:
                log.exception("Recorder tick failed")
                time.sleep(1)

    def _tick(self, cfg: dict, fps: int):
        frame, _, ts = camera.get_frame()
        with self._lock:
            if cfg.get("paused") or frame is None or time.time() - ts > 5:
                # camera lost or privacy pause -> close files cleanly
                if self.continuous or self.event_seg:
                    log.info("Closing recordings (paused or camera unavailable)")
                self._close_continuous()
                self._close_event()
                self._buffer.clear()
                return
            if cfg.get("annotate_recordings"):
                frame = annotate(frame, self.latest_result, draw_zones=False)
            else:
                frame = frame.copy()
            stamp(frame, settings.get("camera.name", "Camera"))

            # pre-event buffer
            pre = float(cfg.get("pre_event_seconds", 5))
            self._buffer.append((time.time(), frame))
            maxlen = int(pre * fps)
            while len(self._buffer) > max(maxlen, 0):
                self._buffer.popleft()

            # continuous
            if cfg.get("continuous_enabled"):
                seg_len = float(cfg.get("segment_minutes", 10)) * 60
                if self.continuous and (time.time() - self.continuous.started >= seg_len or self.continuous.writer.frames == 0 and time.time() - self.continuous.started > 10):
                    self._close_continuous()
                if self.continuous is None:
                    day = CONT_DIR / datetime.now().strftime("%Y-%m-%d")
                    day.mkdir(parents=True, exist_ok=True)
                    path = day / datetime.now().strftime("cont_%Y%m%d_%H%M%S.mp4")
                    self.continuous = _Segment("continuous", path, frame, fps, int(cfg.get("video_crf", 23)))
                    log.info("Continuous segment started: %s", path.name)
                if not self.continuous.write(frame):
                    log.error("Continuous writer failed: %s", self.continuous.writer.error)
                    self._close_continuous()
            elif self.continuous:
                self._close_continuous()

            # event
            if self.event_seg is not None:
                if not cfg.get("event_enabled", True):
                    self._close_event()
                else:
                    self.event_seg.write(frame)
                    too_long = time.time() - self.event_seg.started > float(cfg.get("max_event_minutes", 30)) * 60
                    if (self._event_stop_at and time.time() >= self._event_stop_at) or too_long:
                        self._close_event()


recorder = Recorder()
