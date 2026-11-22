"""Snapshot capture: full-quality original + annotated copy."""
from __future__ import annotations

import logging
import time
from datetime import datetime

import cv2

from .config import SNAP_DIR, settings
from .db import db
from .detector import annotate, stamp

log = logging.getLogger("snapshots")


def save_snapshot(frame, result=None, event_id: int | None = None, label: str = "manual", persons: int = 0) -> dict:
    now = datetime.now()
    day = SNAP_DIR / now.strftime("%Y-%m-%d")
    day.mkdir(parents=True, exist_ok=True)
    base = now.strftime("%Y%m%d_%H%M%S_") + f"{now.microsecond // 1000:03d}_{label}"
    q = int(settings.get("recording.snapshot_quality", 95))
    orig = stamp(frame.copy(), settings.get("camera.name", "Camera"))
    p = day / f"{base}.jpg"
    cv2.imwrite(str(p), orig, [cv2.IMWRITE_JPEG_QUALITY, q])
    ap = None
    if result is not None and result.detections:
        ann = stamp(annotate(frame, result, draw_zones=False), settings.get("camera.name", "Camera"))
        ap = day / f"{base}_ai.jpg"
        cv2.imwrite(str(ap), ann, [cv2.IMWRITE_JPEG_QUALITY, 90])
    h, w = frame.shape[:2]
    sid = db.insert("snapshots", {
        "event_id": event_id, "path": str(p), "annotated_path": str(ap) if ap else None,
        "created_at": time.time(), "label": label, "persons": persons, "width": w, "height": h,
        "size": p.stat().st_size,
    })
    log.info("Snapshot saved: %s", p.name)
    return {"id": sid, "path": str(p), "annotated_path": str(ap) if ap else None}


def latest_snapshot_path() -> str | None:
    r = db.one("SELECT path, annotated_path FROM snapshots ORDER BY id DESC LIMIT 1")
    if not r:
        return None
    return r["annotated_path"] or r["path"]
