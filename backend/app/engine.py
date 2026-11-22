"""Processing engine: runs AI on live frames, manages events, snapshots, recordings and alerts."""
from __future__ import annotations

import json
import logging
import threading
import time

import cv2

from .camera import camera
from .config import settings
from .db import db
from .detector import FrameResult, annotate, detector
from .hub import hub
from .notifier import notifier
from .recorder import recorder
from .snapshots import save_snapshot

log = logging.getLogger("engine")


class Engine:
    def __init__(self):
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.latest: FrameResult | None = None
        self.proc_fps = 0.0
        # active person/object event
        self.event_id: int | None = None
        self.event_started = 0.0
        self.event_last_trigger = 0.0
        self.event_labels: set[str] = set()
        self.event_max_persons = 0
        self.event_max_conf = 0.0
        self.event_snapshots = 0
        self.event_last_snapshot = 0.0
        self.event_kind = "person"
        # misc
        self._motion_frames = 0
        self._last_motion_event = 0.0
        self._label_seen: dict[str, float] = {}
        self._last_storage_alert = 0.0
        self._recent: list[dict] = []
        # streaming
        self._jpeg_lock = threading.Lock()
        self._jpeg = {True: (None, -1), False: (None, -1)}
        self._viewers_ts = 0.0
        self.stream_fps = 0.0

    # ---------- lifecycle ----------
    def start(self):
        camera.on_disconnect = self._on_camera_disconnect
        camera.on_connect = lambda: self._broadcast_status()
        for target, name in ((self._run, "engine"), (self._encoder, "encoder"), (self._status_loop, "status")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self._stop.set()
        self._end_event(force=True)

    # ---------- public ----------
    def status(self) -> dict:
        r = self.latest
        return {
            "persons": r.persons if r else 0,
            "night": r.night if r else False,
            "brightness": round(r.brightness, 1) if r else 0,
            "motion": r.motion if r else False,
            "inference_ms": round(r.inference_ms, 1) if r else 0,
            "processing_fps": round(self.proc_fps, 1),
            "active_event": self.event_id,
            "detections": [d.to_dict(r.width, r.height) for d in r.detections] if r else [],
        }

    def recent_events(self):
        return list(self._recent)

    def manual_snapshot(self) -> dict | None:
        frame, _, _ = camera.get_frame()
        if frame is None:
            return None
        r = self.latest
        snap = save_snapshot(frame, r, label="manual", persons=r.persons if r else 0)
        ev = self._log_event("manual", "Manual snapshot", snapshot_id=snap["id"], persons=r.persons if r else 0)
        db.update("snapshots", snap["id"], {"event_id": ev})
        return snap

    def get_jpeg(self, overlay: bool = True):
        self._viewers_ts = time.time()
        with self._jpeg_lock:
            return self._jpeg[overlay]

    # ---------- streaming encoder ----------
    def _encoder(self):
        last_seq = {True: -1, False: -1}
        cnt, t0 = 0, time.time()
        while not self._stop.is_set():
            if time.time() - self._viewers_ts > 5:
                time.sleep(0.2)
                continue
            frame, seq, _ = camera.get_frame()
            if frame is None or seq == last_seq[True]:
                time.sleep(0.01)
                continue
            for ov in (True, False):
                img = annotate(frame, self.latest) if ov else frame
                h, w = img.shape[:2]
                if w > 1280:
                    img = cv2.resize(img, (1280, int(1280 * h / w)))
                ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    with self._jpeg_lock:
                        self._jpeg[ov] = (buf.tobytes(), seq)
                last_seq[ov] = seq
            cnt += 1
            if time.time() - t0 >= 2:
                self.stream_fps = cnt / (time.time() - t0)
                cnt, t0 = 0, time.time()
            time.sleep(1 / 25)

    # ---------- processing ----------
    def _run(self):
        last_seq = -1
        cnt, t0 = 0, time.time()
        last_bcast = 0.0
        while not self._stop.is_set():
            ifps = max(1.0, float(settings.get("detection.inference_fps", 10)))
            frame, seq, ts = camera.get_frame()
            if frame is None or seq == last_seq:
                if frame is None:
                    self.latest = None
                    if self.event_id:
                        self._end_event(force=True)
                time.sleep(0.02)
                continue
            last_seq = seq
            t_start = time.time()
            try:
                res = detector.process(frame)
                self.latest = res
                recorder.latest_result = res
                self._handle(frame, res)
            except Exception:
                log.exception("Processing error")
                time.sleep(0.5)
            cnt += 1
            if time.time() - t0 >= 2:
                self.proc_fps = cnt / (time.time() - t0)
                cnt, t0 = 0, time.time()
            if time.time() - last_bcast > 0.2:
                last_bcast = time.time()
                hub.broadcast("detections", self.status())
            dt = 1.0 / ifps - (time.time() - t_start)
            if dt > 0:
                time.sleep(dt)

    def _handle(self, frame, res: FrameResult):
        now = res.ts
        cfg_rec = settings.section("recording")
        cfg_det = settings.section("detection")
        alert_objects = set(cfg_det.get("alert_objects", []) or [])
        labels_now = {d.label for d in res.detections if d.category != "face"}
        object_trigger = bool(alert_objects & labels_now) and cfg_rec.get("record_on_objects", True)
        person_trigger = res.persons > 0
        trigger = person_trigger or object_trigger

        # --- main event lifecycle ---
        if trigger:
            if self.event_id is None:
                self._begin_event(frame, res, "person" if person_trigger else "object", labels_now)
            else:
                self.event_last_trigger = now
                recorder.cancel_event_stop()
                if recorder.event_seg is None and cfg_rec.get("event_enabled", True):
                    rid = recorder.start_event(self.event_id, self.event_kind)
                    if rid and not db.one("SELECT recording_id FROM events WHERE id=?", (self.event_id,))["recording_id"]:
                        db.update("events", self.event_id, {"recording_id": rid})
                if person_trigger and self.event_kind != "person":
                    self.event_kind = "person"
                    db.update("events", self.event_id, {"type": "person", "label": "Person detected"})
                self.event_labels |= labels_now
                self.event_max_persons = max(self.event_max_persons, res.persons)
                self.event_max_conf = max([self.event_max_conf] + [d.confidence for d in res.detections if d.category == "person"])
                self._event_snapshot(frame, res)
        elif self.event_id is not None:
            recorder.schedule_event_stop()
            if now - self.event_last_trigger > float(cfg_rec.get("post_event_seconds", 10)):
                self._end_event()

        # --- entry / exit / loitering ---
        for t in res.entered:
            snap = self._event_snapshot(frame, res, force=True)
            sid = self._latest_event_snapshot_id()
            self._log_event("entry", f"Person #{t.id} entered", persons=res.persons, conf=t.confidence, snapshot_id=sid)
            if self.event_id:  # additional person alert (cooldown-limited)
                notifier.notify("person_entered", "👤 Person entered",
                                f"Person entered the camera view. People in view: {res.persons}",
                                image=snap, event_id=self.event_id)
        for t in res.exited:
            dur = t.last_seen - t.first_seen
            self._log_event("exit", f"Person #{t.id} left after {dur:.0f}s", persons=res.persons, details={"duration": dur})
        for t in res.loitering:
            snap = self._event_snapshot(frame, res, force=True)
            self._log_event("loitering", f"Person #{t.id} in area > {cfg_det.get('loiter_seconds', 30)}s",
                            persons=res.persons, snapshot_id=self._latest_event_snapshot_id())
            notifier.notify("person_loitering", "⚠️ Person remaining in area",
                            f"A person has been in view for over {cfg_det.get('loiter_seconds', 30)} seconds.",
                            image=snap, event_id=self.event_id, cooldown_key="loiter")

        # --- vehicles / animals / configured objects ---
        for d in res.detections:
            if d.category in ("person", "face"):
                continue
            if d.category == "object" and d.label not in alert_objects:
                continue
            last = self._label_seen.get(d.label, 0)
            self._label_seen[d.label] = now
            if now - last > 30:
                snap = save_snapshot(frame, res, label=d.label.replace(" ", "_"), persons=res.persons)
                ev = self._log_event(d.category, f"{d.label.title()} detected", conf=d.confidence,
                                     snapshot_id=snap["id"], persons=res.persons, labels=[d.label])
                db.update("snapshots", snap["id"], {"event_id": ev})
                if d.label in alert_objects:
                    notifier.notify("object", f"📦 {d.label.title()} detected",
                                    f"Configured object '{d.label}' appeared ({d.confidence * 100:.0f}%).",
                                    image=snap["annotated_path"] or snap["path"], event_id=ev, cooldown_key=f"obj:{d.label}")

        # --- motion without people ---
        if res.motion and not person_trigger:
            self._motion_frames += 1
        else:
            self._motion_frames = 0
        cd = float(settings.get("notifications.cooldown_seconds", 60))
        if self._motion_frames >= 3 and now - self._last_motion_event > max(cd, 30):
            self._last_motion_event = now
            snap = save_snapshot(frame, None, label="motion", persons=0)
            ev = self._log_event("motion", f"Motion detected ({res.motion_ratio * 100:.1f}% of frame)",
                                 snapshot_id=snap["id"], details={"ratio": res.motion_ratio})
            db.update("snapshots", snap["id"], {"event_id": ev})
            notifier.notify("motion", "🌀 Motion detected", "Motion detected with no person in view.",
                            image=snap["path"], event_id=ev)

    def _begin_event(self, frame, res, kind, labels):
        now = res.ts
        self.event_started = self.event_last_trigger = now
        self.event_kind = kind
        self.event_labels = set(labels)
        self.event_max_persons = res.persons
        self.event_max_conf = max([0.0] + [d.confidence for d in res.detections if d.category in ("person",)])
        self.event_snapshots = 0
        self.event_last_snapshot = 0
        label = "Person detected" if kind == "person" else "Object detected: " + ", ".join(sorted(labels))
        self.event_id = db.insert("events", {
            "type": kind, "label": label, "started_at": now, "max_persons": res.persons,
            "confidence": self.event_max_conf, "labels": sorted(labels),
        })
        snap_path = self._event_snapshot(frame, res, force=True)
        rid = recorder.start_event(self.event_id, kind)
        if rid:
            db.update("events", self.event_id, {"recording_id": rid})
        log.info("Event #%d started (%s, persons=%d)", self.event_id, kind, res.persons)
        ev = self._event_row(self.event_id)
        self._push_recent(ev)
        if kind == "person":
            notifier.notify("person_entered", "🚨 Person detected",
                            f"{res.persons} person(s) detected on {settings.get('camera.name', 'camera')}.",
                            image=snap_path, event_id=self.event_id)

    def _event_snapshot(self, frame, res, force=False) -> str | None:
        if self.event_id is None:
            return None
        cfg = settings.section("recording")
        now = time.time()
        if not force:
            if self.event_snapshots >= int(cfg.get("max_snapshots_per_event", 10)):
                return None
            if now - self.event_last_snapshot < float(cfg.get("snapshot_interval_seconds", 15)):
                return None
        elif now - self.event_last_snapshot < 1.0:
            r = db.one("SELECT path, annotated_path FROM snapshots WHERE event_id=? ORDER BY id DESC LIMIT 1", (self.event_id,))
            return (r["annotated_path"] or r["path"]) if r else None
        snap = save_snapshot(frame, res, event_id=self.event_id, label=self.event_kind, persons=res.persons)
        self.event_snapshots += 1
        self.event_last_snapshot = now
        if self.event_snapshots == 1:
            db.update("events", self.event_id, {"snapshot_id": snap["id"]})
        return snap["annotated_path"] or snap["path"]

    def _latest_event_snapshot_id(self):
        if self.event_id is None:
            return None
        r = db.one("SELECT id FROM snapshots WHERE event_id=? ORDER BY id DESC LIMIT 1", (self.event_id,))
        return r["id"] if r else None

    def _end_event(self, force=False):
        if self.event_id is None:
            return
        eid = self.event_id
        self.event_id = None
        db.update("events", eid, {
            "ended_at": time.time(), "max_persons": self.event_max_persons, "confidence": self.event_max_conf,
            "labels": sorted(self.event_labels),
        })
        if force:
            recorder.schedule_event_stop()
        log.info("Event #%d ended (%.0fs)", eid, time.time() - self.event_started)
        ev = self._event_row(eid)
        self._push_recent(ev)

    def _log_event(self, etype, label, persons=0, conf=None, snapshot_id=None, details=None, labels=None) -> int:
        now = time.time()
        eid = db.insert("events", {
            "type": etype, "label": label, "started_at": now, "ended_at": now, "max_persons": persons,
            "confidence": conf, "snapshot_id": snapshot_id, "labels": labels or [], "details": details,
        })
        self._push_recent(self._event_row(eid))
        return eid

    def _event_row(self, eid):
        ev = db.one("SELECT * FROM events WHERE id=?", (eid,))
        if ev and ev.get("labels"):
            try:
                ev["labels"] = json.loads(ev["labels"])
            except Exception:
                pass
        return ev

    def _push_recent(self, ev):
        if not ev:
            return
        self._recent = [e for e in self._recent if e["id"] != ev["id"]]
        self._recent.insert(0, ev)
        self._recent = self._recent[:30]
        hub.broadcast("event", ev)

    # ---------- system alerts ----------
    def _on_camera_disconnect(self, err):
        self._log_event("camera", f"Camera disconnected: {err}")
        notifier.notify("camera_disconnected", "📷 Camera disconnected",
                        f"The camera stopped responding ({err}). Auto-reconnect is running.")
        self._broadcast_status()

    def on_low_storage(self, st):
        if time.time() - self._last_storage_alert < 6 * 3600:
            return
        self._last_storage_alert = time.time()
        free_gb = st["disk_free"] / 1e9
        self._log_event("storage", f"Low storage: {free_gb:.1f} GB free")
        notifier.notify("storage_low", "💾 Storage running low",
                        f"Only {free_gb:.1f} GB free. Old recordings will be cleaned up automatically.", force=False)

    def _broadcast_status(self):
        from .system import system_status
        hub.broadcast("status", system_status())

    def _status_loop(self):
        while not self._stop.is_set():
            try:
                self._broadcast_status()
            except Exception:
                log.exception("status broadcast failed")
            self._stop.wait(2)


engine = Engine()
