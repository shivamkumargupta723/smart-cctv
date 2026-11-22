"""Settings management with encrypted secrets.

Settings live in config/settings.json. Any secret field (tokens, passwords)
is encrypted with a Fernet key stored in config/.secret.key (chmod 600).
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DB_DIR = ROOT / "database"
MODELS_DIR = ROOT / "models"
REC_DIR = ROOT / "recordings"
CONT_DIR = REC_DIR / "continuous"
EVENT_DIR = REC_DIR / "events"
SNAP_DIR = ROOT / "snapshots"
LOG_DIR = ROOT / "logs"
EXPORT_DIR = ROOT / "exports"
FRONTEND_DIST = ROOT / "frontend" / "dist"

for d in (CONFIG_DIR, DB_DIR, MODELS_DIR, CONT_DIR, EVENT_DIR, SNAP_DIR, LOG_DIR, EXPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = CONFIG_DIR / "settings.json"
KEY_FILE = CONFIG_DIR / ".secret.key"

# Paths (dot-notation) of secret values that must be encrypted at rest
SECRET_FIELDS = [
    "notifications.telegram.bot_token",
    "notifications.ntfy.token",
    "notifications.whatsapp.access_token",
    "notifications.email.password",
]
SECRET_MASK = "••••••••"

DEFAULTS: dict[str, Any] = {
    "server": {"host": "127.0.0.1", "port": 8090, "session_hours": 72},
    "camera": {
        "source": "auto",          # "auto", camera index ("0","1"), or RTSP/HTTP URL
        "width": 1280,
        "height": 720,
        "fps": 30,
        "flip_horizontal": False,
        "rotate": 0,               # 0, 90, 180, 270
        "reconnect_seconds": 3,
        "name": "Camera 1",
    },
    "detection": {
        "enabled": True,
        "model": "yolo11n.pt",
        "device": "auto",          # auto, mps, cpu, cuda
        "imgsz": 640,
        "inference_fps": 10,
        "person_confidence": 0.5,
        "object_confidence": 0.45,
        "detect_persons": True,
        "detect_vehicles": True,
        "detect_animals": True,
        "detect_objects": True,
        "detect_faces": True,
        "alert_objects": [],       # COCO class names that trigger alerts/recording (besides person)
        "motion_enabled": True,
        "motion_sensitivity": 50,  # 1..100 (higher = more sensitive)
        "motion_min_area": 0.005,  # fraction of frame
        "person_confirm_frames": 2,
        "exit_timeout_seconds": 3.0,
        "loiter_seconds": 30,
        "zones": [],               # [{id,name,type:"detect"|"ignore",points:[[x,y],...] normalized}]
        "night_mode": "auto",      # auto, day, night
        "night_brightness_threshold": 60,
        "night_person_confidence": 0.4,
        "night_enhance": True,
    },
    "recording": {
        "paused": False,           # privacy pause: stops all capture & recording
        "continuous_enabled": False,
        "event_enabled": True,
        "segment_minutes": 10,
        "record_fps": 15,
        "pre_event_seconds": 5,
        "post_event_seconds": 10,
        "max_event_minutes": 30,
        "record_on_objects": True,  # alert_objects also trigger event recording
        "annotate_recordings": False,
        "video_crf": 23,
        "snapshot_interval_seconds": 15,
        "max_snapshots_per_event": 10,
        "snapshot_quality": 95,
    },
    "storage": {
        "retention_continuous_days": 7,
        "retention_events_days": 30,
        "retention_snapshots_days": 30,
        "min_free_gb": 5,
        "low_storage_alert_gb": 10,
        "auto_cleanup": True,
    },
    "notifications": {
        "cooldown_seconds": 60,
        "triggers": {
            "person_entered": True,
            "person_loitering": True,
            "motion": False,
            "object": True,
            "camera_disconnected": True,
            "storage_low": True,
        },
        "browser": {"enabled": True},
        "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
        "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": "", "token": "", "priority": 4},
        "whatsapp": {"enabled": False, "access_token": "", "phone_number_id": "", "recipient": "", "api_version": "v21.0"},
        "email": {"enabled": False, "smtp_host": "", "smtp_port": 587, "use_tls": True, "username": "", "password": "", "from_addr": "", "to_addr": ""},
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _get_path(d: dict, path: str):
    cur = d
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _set_path(d: dict, path: str, value):
    parts = path.split(".")
    cur = d
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def _load_key() -> bytes:
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes().strip()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    os.chmod(KEY_FILE, 0o600)
    return key


class Settings:
    def __init__(self):
        self._lock = threading.RLock()
        self._fernet = Fernet(_load_key())
        self._data = copy.deepcopy(DEFAULTS)
        self._listeners = []
        self.load()

    # ---------- persistence ----------
    def load(self):
        with self._lock:
            raw = {}
            if SETTINGS_FILE.exists():
                try:
                    raw = json.loads(SETTINGS_FILE.read_text())
                except Exception:
                    raw = {}
            data = _deep_merge(DEFAULTS, raw)
            for f in SECRET_FIELDS:
                v = _get_path(data, f)
                if isinstance(v, str) and v.startswith("enc:"):
                    try:
                        _set_path(data, f, self._fernet.decrypt(v[4:].encode()).decode())
                    except InvalidToken:
                        _set_path(data, f, "")
            self._data = data
            self.save()

    def save(self):
        with self._lock:
            out = copy.deepcopy(self._data)
            for f in SECRET_FIELDS:
                v = _get_path(out, f)
                if v:
                    _set_path(out, f, "enc:" + self._fernet.encrypt(str(v).encode()).decode())
            tmp = SETTINGS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(out, indent=2))
            os.chmod(tmp, 0o600)
            tmp.replace(SETTINGS_FILE)

    # ---------- access ----------
    def get(self, path: str, default=None):
        with self._lock:
            v = _get_path(self._data, path)
            return default if v is None else copy.deepcopy(v)

    def section(self, name: str) -> dict:
        return self.get(name, {})

    def all(self, masked: bool = True) -> dict:
        with self._lock:
            out = copy.deepcopy(self._data)
        if masked:
            for f in SECRET_FIELDS:
                if _get_path(out, f):
                    _set_path(out, f, SECRET_MASK)
        return out

    def update(self, section: str, values: dict) -> dict:
        """Update a top-level section. Masked secrets are kept unchanged."""
        if section not in DEFAULTS:
            raise KeyError(section)
        with self._lock:
            current = self._data[section]
            merged = _deep_merge(current, values or {})
            for f in SECRET_FIELDS:
                if f.startswith(section + "."):
                    sub = f[len(section) + 1:]
                    if _get_path(merged, sub) == SECRET_MASK:
                        _set_path(merged, sub, _get_path(current, sub))
            self._data[section] = merged
            self.save()
        for cb in list(self._listeners):
            try:
                cb(section)
            except Exception:
                pass
        return self.all()[section]

    def on_change(self, cb):
        self._listeners.append(cb)


settings = Settings()
