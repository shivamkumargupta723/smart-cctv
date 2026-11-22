"""Application logging: rotating file + in-memory ring buffer for the dashboard."""
from __future__ import annotations

import collections
import logging
import logging.handlers
import threading
import time

from .config import LOG_DIR

LOG_FILE = LOG_DIR / "cctv.log"
_ring: collections.deque = collections.deque(maxlen=3000)
_ring_lock = threading.Lock()
_seq = 0


class RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        global _seq
        try:
            msg = record.getMessage()
            if record.exc_info:
                msg += "\n" + logging.Formatter().formatException(record.exc_info)
            with _ring_lock:
                _seq += 1
                _ring.append({
                    "id": _seq,
                    "ts": record.created,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": msg,
                })
        except Exception:
            pass


def setup_logging():
    root = logging.getLogger()
    if getattr(root, "_cctv_configured", False):
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=5)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)
    root.addHandler(RingHandler())
    for noisy in ("uvicorn.access", "httpx", "httpcore", "ultralytics", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._cctv_configured = True


def get_logs(level: str | None = None, since_id: int = 0, limit: int = 500, search: str | None = None):
    order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    min_lvl = order.get((level or "").upper(), 0)
    with _ring_lock:
        items = list(_ring)
    out = [
        r for r in items
        if r["id"] > since_id
        and order.get(r["level"], 0) >= min_lvl
        and (not search or search.lower() in r["message"].lower() or search.lower() in r["logger"].lower())
    ]
    return out[-limit:]


def uptime_start() -> float:
    return _START


_START = time.time()
