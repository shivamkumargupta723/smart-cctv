"""Storage stats, retention cleanup and low-space protection."""
from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from pathlib import Path

from .config import CONT_DIR, EVENT_DIR, EXPORT_DIR, LOG_DIR, ROOT, SNAP_DIR, settings
from .db import db

log = logging.getLogger("storage")


def dir_size(p: Path) -> int:
    total = 0
    for root, _, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _rm(path: str | None):
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except Exception as e:
        log.warning("Could not delete %s: %s", path, e)


def delete_recording(rec: dict):
    _rm(rec["path"])
    _rm(rec.get("thumb_path"))
    db.execute("DELETE FROM recordings WHERE id=?", (rec["id"],))
    db.execute("UPDATE events SET recording_id=NULL WHERE recording_id=?", (rec["id"],))


def delete_snapshot(s: dict):
    _rm(s["path"])
    _rm(s.get("annotated_path"))
    db.execute("DELETE FROM snapshots WHERE id=?", (s["id"],))
    db.execute("UPDATE events SET snapshot_id=NULL WHERE snapshot_id=?", (s["id"],))


def delete_event(ev_id: int, with_media: bool = True):
    if with_media:
        for s in db.query("SELECT * FROM snapshots WHERE event_id=?", (ev_id,)):
            delete_snapshot(s)
        for r in db.query("SELECT * FROM recordings WHERE event_id=? AND status!='recording'", (ev_id,)):
            delete_recording(r)
    db.execute("DELETE FROM events WHERE id=?", (ev_id,))


class StorageManager:
    def __init__(self):
        self._stop = threading.Event()
        self._thread = None
        self._cache = None
        self._cache_ts = 0
        self.on_low_storage = None
        self.last_cleanup = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name="storage", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def stats(self, fresh: bool = False) -> dict:
        if not fresh and self._cache and time.time() - self._cache_ts < 30:
            return self._cache
        du = shutil.disk_usage(ROOT)
        folders = {
            "continuous": dir_size(CONT_DIR), "events": dir_size(EVENT_DIR), "snapshots": dir_size(SNAP_DIR),
            "logs": dir_size(LOG_DIR), "exports": dir_size(EXPORT_DIR),
        }
        counts = {
            "continuous": db.one("SELECT COUNT(*) c FROM recordings WHERE kind='continuous'")["c"],
            "events": db.one("SELECT COUNT(*) c FROM recordings WHERE kind='event'")["c"],
            "snapshots": db.one("SELECT COUNT(*) c FROM snapshots")["c"],
            "event_rows": db.one("SELECT COUNT(*) c FROM events")["c"],
        }
        low_gb = float(settings.get("storage.low_storage_alert_gb", 10))
        self._cache = {
            "disk_total": du.total, "disk_used": du.used, "disk_free": du.free,
            "percent_used": round((du.total - du.free) / du.total * 100, 1), "folders": folders,
            "cctv_total": sum(folders.values()), "counts": counts,
            "low": du.free / 1e9 < low_gb, "last_cleanup": self.last_cleanup,
        }
        self._cache_ts = time.time()
        return self._cache

    def cleanup(self) -> dict:
        cfg = settings.section("storage")
        now = time.time()
        removed = {"continuous": 0, "events": 0, "snapshots": 0, "low_space": 0, "event_rows": 0}
        rules = [("continuous", cfg.get("retention_continuous_days", 7)), ("event", cfg.get("retention_events_days", 30))]
        for kind, days in rules:
            if not days or days <= 0:
                continue
            cutoff = now - float(days) * 86400
            for r in db.query("SELECT * FROM recordings WHERE kind=? AND started_at<? AND status!='recording'", (kind, cutoff)):
                delete_recording(r)
                removed["continuous" if kind == "continuous" else "events"] += 1
        sdays = cfg.get("retention_snapshots_days", 30)
        if sdays and sdays > 0:
            for s in db.query("SELECT * FROM snapshots WHERE created_at<?", (now - float(sdays) * 86400,)):
                delete_snapshot(s)
                removed["snapshots"] += 1
        edays = max(float(cfg.get("retention_events_days", 30) or 0), float(sdays or 0))
        if edays > 0:
            n = db.one("SELECT COUNT(*) c FROM events WHERE started_at<?", (now - edays * 86400,))["c"]
            db.execute("DELETE FROM events WHERE started_at<?", (now - edays * 86400,))
            removed["event_rows"] = n
        db.execute("DELETE FROM notifications WHERE created_at<?", (now - 90 * 86400,))
        # Low disk: delete oldest continuous, then oldest event recordings
        min_free = float(cfg.get("min_free_gb", 5)) * 1e9
        for kind in ("continuous", "event"):
            while shutil.disk_usage(ROOT).free < min_free:
                r = db.one("SELECT * FROM recordings WHERE kind=? AND status!='recording' ORDER BY started_at LIMIT 1", (kind,))
                if not r:
                    break
                delete_recording(r)
                removed["low_space"] += 1
        # stray empty day folders
        for base in (CONT_DIR, EVENT_DIR, SNAP_DIR):
            for d in base.iterdir():
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
        for f in EXPORT_DIR.glob("*.zip"):
            if now - f.stat().st_mtime > 3600:
                f.unlink(missing_ok=True)
        self.last_cleanup = now
        if any(removed.values()):
            log.info("Cleanup removed: %s", removed)
        self._cache = None
        return removed

    def _run(self):
        last_clean = 0
        while not self._stop.is_set():
            try:
                st = self.stats(fresh=True)
                if st["low"] and self.on_low_storage:
                    self.on_low_storage(st)
                if settings.get("storage.auto_cleanup", True) and time.time() - last_clean > 3600:
                    self.cleanup()
                    last_clean = time.time()
                elif st["disk_free"] < float(settings.get("storage.min_free_gb", 5)) * 1e9:
                    self.cleanup()
            except Exception:
                log.exception("Storage loop error")
            self._stop.wait(300)


storage = StorageManager()
