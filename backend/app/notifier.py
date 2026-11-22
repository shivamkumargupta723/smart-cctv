"""Notification dispatcher: Browser (WebSocket), Telegram, ntfy (mobile push), WhatsApp Cloud API, Email."""
from __future__ import annotations

import logging
import mimetypes
import queue
import smtplib
import ssl
import threading
import time
from email.message import EmailMessage
from pathlib import Path

import httpx

from .config import settings
from .db import db
from .hub import hub

log = logging.getLogger("notifier")
CHANNELS = ["browser", "telegram", "ntfy", "whatsapp", "email"]


class Notifier:
    def __init__(self):
        self._q: queue.Queue = queue.Queue(maxsize=200)
        self._last: dict[str, float] = {}
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        self._thread = threading.Thread(target=self._run, name="notifier", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._q.put(None)

    def status(self) -> dict:
        cfg = settings.section("notifications")
        out = {}
        for ch in CHANNELS:
            c = cfg.get(ch, {})
            out[ch] = {"enabled": bool(c.get("enabled")), "configured": self._configured(ch, c)}
        last = db.one("SELECT * FROM notifications ORDER BY id DESC LIMIT 1")
        return {"channels": out, "last": last, "queue": self._q.qsize()}

    @staticmethod
    def _configured(ch: str, c: dict) -> bool:
        if ch == "browser":
            return True
        if ch == "telegram":
            return bool(c.get("bot_token") and c.get("chat_id"))
        if ch == "ntfy":
            return bool(c.get("topic"))
        if ch == "whatsapp":
            return bool(c.get("access_token") and c.get("phone_number_id") and c.get("recipient"))
        if ch == "email":
            return bool(c.get("smtp_host") and c.get("to_addr"))
        return False

    def notify(self, trigger: str, title: str, message: str, image: str | None = None,
               event_id: int | None = None, cooldown_key: str | None = None, force: bool = False):
        cfg = settings.section("notifications")
        if not force and not cfg.get("triggers", {}).get(trigger, False):
            return False
        key = cooldown_key or trigger
        cd = float(cfg.get("cooldown_seconds", 60))
        now = time.time()
        if not force and now - self._last.get(key, 0) < cd:
            log.debug("Notification %s suppressed by cooldown", key)
            return False
        self._last[key] = now
        try:
            self._q.put_nowait({"trigger": trigger, "title": title, "message": message, "image": image,
                                "event_id": event_id, "ts": now, "channels": None})
        except queue.Full:
            log.warning("Notification queue full, dropping %s", trigger)
            return False
        return True

    def test(self, channel: str) -> dict:
        """Synchronously send a test message on one channel."""
        from .snapshots import latest_snapshot_path
        img = latest_snapshot_path()
        item = {"trigger": "test", "title": "Smart CCTV test notification",
                "message": f"Test message from Smart CCTV at {time.strftime('%Y-%m-%d %H:%M:%S')}",
                "image": img, "event_id": None, "ts": time.time()}
        return self._send_one(channel, item, require_enabled=False)

    # ---------- worker ----------
    def _run(self):
        while not self._stop.is_set():
            item = self._q.get()
            if item is None:
                break
            for ch in CHANNELS:
                try:
                    self._send_one(ch, item, require_enabled=True)
                except Exception:
                    log.exception("Notification channel %s crashed", ch)

    def _send_one(self, ch: str, item: dict, require_enabled: bool) -> dict:
        cfg = settings.section("notifications").get(ch, {})
        if require_enabled and not cfg.get("enabled"):
            return {"status": "skipped"}
        if not self._configured(ch, cfg):
            res = {"status": "failed", "error": f"{ch} is not configured"}
            if not require_enabled:
                self._record(ch, item, res)
            return res
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(item["ts"]))
        text = f"{item['title']}\n{item['message']}\n🕒 {stamp}"
        image = item.get("image") if item.get("image") and Path(item["image"]).exists() else None
        try:
            if ch == "browser":
                hub.broadcast("notification", {"title": item["title"], "message": item["message"], "ts": item["ts"],
                                               "trigger": item["trigger"], "event_id": item.get("event_id")})
            elif ch == "telegram":
                self._telegram(cfg, text, image)
            elif ch == "ntfy":
                self._ntfy(cfg, item, stamp, image)
            elif ch == "whatsapp":
                self._whatsapp(cfg, text, image)
            elif ch == "email":
                self._email(cfg, item, text, image)
            res = {"status": "sent"}
        except Exception as e:
            err = str(e)
            if isinstance(e, httpx.HTTPStatusError):
                err = f"HTTP {e.response.status_code}: {e.response.text[:300]}"
            log.error("Notification via %s failed: %s", ch, err)
            res = {"status": "failed", "error": err}
        self._record(ch, item, res)
        return res

    def _record(self, ch, item, res):
        db.insert("notifications", {
            "created_at": time.time(), "trigger": item["trigger"], "channel": ch, "title": item["title"],
            "message": item["message"], "status": res["status"], "error": res.get("error"), "event_id": item.get("event_id"),
        })

    # ---------- channels ----------
    @staticmethod
    def _telegram(cfg, text, image):
        base = f"https://api.telegram.org/bot{cfg['bot_token']}"
        with httpx.Client(timeout=30) as c:
            if image:
                with open(image, "rb") as f:
                    r = c.post(f"{base}/sendPhoto", data={"chat_id": cfg["chat_id"], "caption": text[:1000]},
                               files={"photo": (Path(image).name, f, "image/jpeg")})
            else:
                r = c.post(f"{base}/sendMessage", data={"chat_id": cfg["chat_id"], "text": text})
            r.raise_for_status()

    @staticmethod
    def _ntfy(cfg, item, stamp, image):
        url = cfg.get("server", "https://ntfy.sh").rstrip("/") + "/" + cfg["topic"].strip("/")
        headers = {
            "Title": item["title"].encode("ascii", "ignore").decode().strip() or "Smart CCTV",
            "Priority": str(cfg.get("priority", 4)),
            "Tags": "rotating_light" if item["trigger"] in ("person_entered", "person_loitering") else "camera",
        }
        if cfg.get("token"):
            headers["Authorization"] = f"Bearer {cfg['token']}"
        msg = f"{item['message']} ({stamp})"
        with httpx.Client(timeout=30) as c:
            if image:
                headers["Filename"] = Path(image).name
                headers["Message"] = msg.encode("ascii", "ignore").decode()
                with open(image, "rb") as f:
                    r = c.put(url, content=f.read(), headers=headers)
            else:
                r = c.post(url, content=msg.encode(), headers=headers)
            r.raise_for_status()

    @staticmethod
    def _whatsapp(cfg, text, image):
        ver = cfg.get("api_version", "v21.0")
        base = f"https://graph.facebook.com/{ver}/{cfg['phone_number_id']}"
        headers = {"Authorization": f"Bearer {cfg['access_token']}"}
        to = "".join(ch for ch in cfg["recipient"] if ch.isdigit())
        with httpx.Client(timeout=30, headers=headers) as c:
            payload = {"messaging_product": "whatsapp", "to": to}
            if image:
                with open(image, "rb") as f:
                    up = c.post(f"{base}/media", data={"messaging_product": "whatsapp", "type": "image/jpeg"},
                                files={"file": (Path(image).name, f, "image/jpeg")})
                up.raise_for_status()
                payload.update({"type": "image", "image": {"id": up.json()["id"], "caption": text[:1000]}})
            else:
                payload.update({"type": "text", "text": {"body": text}})
            r = c.post(f"{base}/messages", json=payload)
            r.raise_for_status()

    @staticmethod
    def _email(cfg, item, text, image):
        msg = EmailMessage()
        msg["Subject"] = f"[Smart CCTV] {item['title']}"
        msg["From"] = cfg.get("from_addr") or cfg.get("username")
        msg["To"] = cfg["to_addr"]
        msg.set_content(text)
        if image:
            ctype = mimetypes.guess_type(image)[0] or "image/jpeg"
            maintype, subtype = ctype.split("/")
            with open(image, "rb") as f:
                msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=Path(image).name)
        port = int(cfg.get("smtp_port", 587))
        ctx = ssl.create_default_context()
        if port == 465:
            server = smtplib.SMTP_SSL(cfg["smtp_host"], port, context=ctx, timeout=30)
        else:
            server = smtplib.SMTP(cfg["smtp_host"], port, timeout=30)
            if cfg.get("use_tls", True):
                server.starttls(context=ctx)
        try:
            if cfg.get("username"):
                server.login(cfg["username"], cfg.get("password", ""))
            server.send_message(msg)
        finally:
            server.quit()


notifier = Notifier()
