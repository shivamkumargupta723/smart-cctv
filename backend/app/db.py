"""SQLite database layer (thread-safe, WAL mode)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any

from .config import DB_DIR

DB_PATH = DB_DIR / "cctv.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,             -- person, motion, object, vehicle, animal, entry, exit, loitering, camera, storage, system
    label TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    max_persons INTEGER DEFAULT 0,
    confidence REAL,
    labels TEXT,                    -- JSON list of labels seen
    snapshot_id INTEGER,
    recording_id INTEGER,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_started ON events(started_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    path TEXT NOT NULL,
    annotated_path TEXT,
    created_at REAL NOT NULL,
    label TEXT,
    persons INTEGER DEFAULT 0,
    width INTEGER, height INTEGER,
    size INTEGER
);
CREATE INDEX IF NOT EXISTS idx_snap_created ON snapshots(created_at);
CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,             -- continuous | event
    event_id INTEGER,
    path TEXT NOT NULL,
    thumb_path TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    duration REAL,
    size INTEGER,
    status TEXT DEFAULT 'recording' -- recording | complete | failed
);
CREATE INDEX IF NOT EXISTS idx_rec_started ON recordings(started_at);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at REAL NOT NULL,
    trigger TEXT NOT NULL,
    channel TEXT NOT NULL,
    title TEXT,
    message TEXT,
    status TEXT,                    -- sent | failed | skipped
    error TEXT,
    event_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_notif_created ON notifications(created_at);
"""


class Database:
    def __init__(self, path=DB_PATH):
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        # Recordings left 'recording' after crash -> mark failed
        self.execute("UPDATE recordings SET status='failed' WHERE status='recording'")
        self.execute("UPDATE events SET ended_at=started_at WHERE ended_at IS NULL")

    def execute(self, sql: str, params: tuple | list = ()) -> int:
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    def query(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | list = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def insert(self, table: str, data: dict[str, Any]) -> int:
        cols = ",".join(data.keys())
        qs = ",".join("?" for _ in data)
        vals = [json.dumps(v) if isinstance(v, (list, dict)) else v for v in data.values()]
        return self.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", vals)

    def update(self, table: str, row_id: int, data: dict[str, Any]):
        if not data:
            return
        sets = ",".join(f"{k}=?" for k in data)
        vals = [json.dumps(v) if isinstance(v, (list, dict)) else v for v in data.values()]
        self.execute(f"UPDATE {table} SET {sets} WHERE id=?", [*vals, row_id])

    def cleanup_sessions(self):
        self.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))


db = Database()
