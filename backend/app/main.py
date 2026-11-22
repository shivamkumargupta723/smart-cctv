"""Smart CCTV — FastAPI application (API, MJPEG stream, WebSocket, dashboard)."""
from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
import time
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import cv2
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .logs import LOG_FILE, get_logs, setup_logging

setup_logging()

from . import auth  # noqa: E402
from .camera import camera, probe_cameras  # noqa: E402
from .config import EXPORT_DIR, FRONTEND_DIST, MODELS_DIR, settings  # noqa: E402
from .db import db  # noqa: E402
from .detector import detector  # noqa: E402
from .engine import engine  # noqa: E402
from .hub import hub  # noqa: E402
from .notifier import CHANNELS, notifier  # noqa: E402
from .recorder import recorder  # noqa: E402
from .storage import delete_event, delete_recording, delete_snapshot, storage  # noqa: E402
from .system import hardware_info, recommended_model, system_status  # noqa: E402

log = logging.getLogger("app")
MODELS = [
    {"file": "yolo11n.pt", "name": "YOLO11 Nano", "size_mb": 5.4, "note": "Fastest — any Mac"},
    {"file": "yolo11s.pt", "name": "YOLO11 Small", "size_mb": 19, "note": "Balanced — Apple Silicon recommended"},
    {"file": "yolo11m.pt", "name": "YOLO11 Medium", "size_mb": 39, "note": "Most accurate — M-series Pro/Max, 16GB+"},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.bind(asyncio.get_running_loop())
    hw = hardware_info()
    log.info("Smart CCTV starting on %s | %s | %s cores | %s GB RAM | accel=%s",
             hw["os"], hw["chip"], hw["cpu_cores"], hw["ram_gb"], hw["accelerator"])
    detector.load()
    storage.on_low_storage = engine.on_low_storage
    camera.start()
    recorder.start()
    notifier.start()
    engine.start()
    storage.start()
    log.info("Dashboard ready at http://localhost:%s", settings.get("server.port", 8090))
    yield
    log.info("Shutting down ...")
    engine.stop()
    recorder.stop()
    camera.stop()
    notifier.stop()
    storage.stop()


app = FastAPI(title="Smart CCTV", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": f"Internal error: {exc}"}, status_code=500)


User = Depends(auth.require_user)


def _decode(rows: list[dict], fields=("labels", "details")):
    for r in rows:
        for f in fields:
            if r.get(f) and isinstance(r[f], str):
                try:
                    r[f] = json.loads(r[f])
                except Exception:
                    pass
    return rows


# ====================== AUTH ======================
@app.get("/api/auth/state")
def auth_state(request: Request):
    user = auth._user_for_token(request.cookies.get(auth.COOKIE_NAME))
    return {"setup_required": not auth.has_users(), "user": user}


def _set_cookie(resp: Response, token: str):
    resp.set_cookie(auth.COOKIE_NAME, token, httponly=True, samesite="strict",
                    max_age=int(settings.get("server.session_hours", 72) * 3600), path="/")


@app.post("/api/auth/setup")
def auth_setup(response: Response, payload: dict = Body(...)):
    if auth.has_users():
        raise HTTPException(400, "Already configured")
    username = (payload.get("username") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,64}", username):
        raise HTTPException(400, "Username must be 3-64 characters (letters, digits, _ . @ -)")
    uid = auth.create_user(username, payload.get("password") or "")
    _set_cookie(response, auth.create_session(uid))
    log.info("Admin account '%s' created", username)
    return {"ok": True}


@app.post("/api/auth/login")
def auth_login(request: Request, response: Response, payload: dict = Body(...)):
    ip = request.client.host if request.client else "?"
    auth.check_rate_limit(ip)
    u = auth.authenticate(payload.get("username") or "", payload.get("password") or "")
    if not u:
        auth.record_failed(ip)
        log.warning("Failed login for '%s' from %s", payload.get("username"), ip)
        raise HTTPException(401, "Invalid username or password")
    _set_cookie(response, auth.create_session(u["id"]))
    log.info("User '%s' logged in from %s", u["username"], ip)
    return {"ok": True}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    tok = request.cookies.get(auth.COOKIE_NAME)
    if tok:
        auth.delete_session(tok)
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return {"ok": True}


@app.post("/api/auth/password")
def change_password(payload: dict = Body(...), user=User):
    u = db.one("SELECT * FROM users WHERE id=?", (user["id"],))
    if not auth.verify_password(payload.get("current") or "", u["password_hash"]):
        raise HTTPException(400, "Current password is incorrect")
    auth.validate_password(payload.get("new") or "")
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (auth.hash_password(payload["new"]), user["id"]))
    log.info("Password changed for '%s'", user["username"])
    return {"ok": True}


# ====================== STATUS / STREAM ======================
@app.get("/api/status")
def status(user=User):
    s = system_status()
    s["live"] = engine.status()
    s["recent_events"] = engine.recent_events()[:15]
    return s


@app.get("/api/system/hardware")
def hardware(user=User):
    return hardware_info() | {"recommended_model": recommended_model()}


@app.get("/api/stream")
async def stream(request: Request, overlay: int = 1, user=User):
    boundary = "frame"

    async def gen():
        last = -1
        idle = 0
        while True:
            if await request.is_disconnected():
                break
            jpg, seq = engine.get_jpeg(bool(overlay))
            if jpg is None or seq == last:
                await asyncio.sleep(0.02)
                idle += 1
                if idle > 250 and jpg is not None:  # resend last frame every ~5s to keep connection alive
                    idle = 0
                    yield b"--" + boundary.encode() + b"\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                continue
            idle = 0
            last = seq
            yield (b"--" + boundary.encode() + b"\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                   str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")

    return StreamingResponse(gen(), media_type=f"multipart/x-mixed-replace; boundary={boundary}",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/frame.jpg")
def frame_jpg(overlay: int = 0, user=User):
    frame, _, _ = camera.get_frame()
    if frame is None:
        raise HTTPException(503, "Camera not available")
    from .detector import annotate
    img = annotate(frame, engine.latest) if overlay else frame
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    origin = ws.headers.get("origin", "")
    host = ws.headers.get("host", "")
    if origin and re.sub(r"^https?://", "", origin) != host:
        await ws.close(code=4403)
        return
    if not auth.ws_user(ws):
        await ws.close(code=4401)
        return
    await ws.accept()
    await hub.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "status", "data": system_status()}, default=str))
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.remove(ws)


# ====================== EVENTS ======================
def _range_filters(where, params, col, start, end):
    if start:
        where.append(f"{col}>=?")
        params.append(start)
    if end:
        where.append(f"{col}<=?")
        params.append(end)


@app.get("/api/events")
def list_events(type: str | None = None, q: str | None = None, start: float | None = None, end: float | None = None,
                limit: int = Query(50, le=500), offset: int = 0, user=User):
    where, params = [], []
    if type:
        types = [t for t in type.split(",") if t]
        where.append(f"e.type IN ({','.join('?' * len(types))})")
        params += types
    if q:
        where.append("(e.label LIKE ? OR e.labels LIKE ? OR e.type LIKE ?)")
        params += [f"%{q}%"] * 3
    _range_filters(where, params, "e.started_at", start, end)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.one(f"SELECT COUNT(*) c FROM events e {w}", params)["c"]
    rows = db.query(f"""SELECT e.*, r.status AS recording_status,
                        (SELECT COUNT(*) FROM snapshots x WHERE x.event_id=e.id) AS snapshot_count
                        FROM events e LEFT JOIN recordings r ON r.id=e.recording_id
                        {w} ORDER BY e.started_at DESC LIMIT ? OFFSET ?""", params + [limit, offset])
    return {"total": total, "items": _decode(rows)}


@app.get("/api/events/stats")
def event_stats(user=User):
    day_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    by_type = {r["type"]: r["c"] for r in db.query("SELECT type, COUNT(*) c FROM events WHERE started_at>=? GROUP BY type", (day_start,))}
    since = time.time() - 24 * 3600
    rows = db.query("SELECT started_at, type FROM events WHERE started_at>=? AND type IN ('person','motion','vehicle','animal','object')", (since,))
    hours = [{"hour": i, "person": 0, "motion": 0, "other": 0} for i in range(24)]
    for r in rows:
        idx = min(23, int((r["started_at"] - since) // 3600))
        k = r["type"] if r["type"] in ("person", "motion") else "other"
        hours[idx][k] += 1
    return {"today": by_type, "hourly": hours, "hourly_start": since,
            "total_events": db.one("SELECT COUNT(*) c FROM events")["c"]}


@app.get("/api/events/{eid}")
def get_event(eid: int, user=User):
    ev = db.one("SELECT * FROM events WHERE id=?", (eid,))
    if not ev:
        raise HTTPException(404, "Event not found")
    _decode([ev])
    ev["snapshots"] = db.query("SELECT id, created_at, label, persons FROM snapshots WHERE event_id=? ORDER BY created_at", (eid,))
    ev["recordings"] = db.query("SELECT id, kind, started_at, duration, size, status FROM recordings WHERE event_id=? ORDER BY started_at", (eid,))
    return ev


@app.delete("/api/events/{eid}")
def del_event(eid: int, media: int = 1, user=User):
    if eid == engine.event_id:
        raise HTTPException(409, "Event is still in progress")
    delete_event(eid, bool(media))
    return {"ok": True}


@app.post("/api/events/delete")
def del_events(payload: dict = Body(...), user=User):
    n = 0
    for eid in payload.get("ids", []):
        if eid != engine.event_id:
            delete_event(int(eid), bool(payload.get("media", True)))
            n += 1
    log.info("Deleted %d events", n)
    return {"deleted": n}


# ====================== SNAPSHOTS ======================
@app.get("/api/snapshots")
def list_snapshots(event_id: int | None = None, label: str | None = None, start: float | None = None,
                   end: float | None = None, limit: int = Query(60, le=500), offset: int = 0, user=User):
    where, params = [], []
    if event_id:
        where.append("event_id=?")
        params.append(event_id)
    if label:
        where.append("label=?")
        params.append(label)
    _range_filters(where, params, "created_at", start, end)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.one(f"SELECT COUNT(*) c FROM snapshots {w}", params)["c"]
    rows = db.query(f"SELECT id, event_id, created_at, label, persons, width, height, size, annotated_path IS NOT NULL AS has_annotated FROM snapshots {w} ORDER BY created_at DESC LIMIT ? OFFSET ?", params + [limit, offset])
    labels = [r["label"] for r in db.query("SELECT DISTINCT label FROM snapshots ORDER BY label")]
    return {"total": total, "items": rows, "labels": labels}


def _snap(sid: int) -> dict:
    s = db.one("SELECT * FROM snapshots WHERE id=?", (sid,))
    if not s:
        raise HTTPException(404, "Snapshot not found")
    return s


@app.get("/api/snapshots/{sid}/image")
def snapshot_image(sid: int, annotated: int = 0, thumb: int = 0, download: int = 0, user=User):
    s = _snap(sid)
    path = Path(s["annotated_path"] if annotated and s["annotated_path"] else s["path"])
    if not path.exists():
        raise HTTPException(404, "File missing")
    if thumb:
        tp = path.with_name(path.stem + "_thumb.jpg")
        if not tp.exists():
            img = cv2.imread(str(path))
            if img is None:
                raise HTTPException(500, "Cannot read image")
            h, w = img.shape[:2]
            cv2.imwrite(str(tp), cv2.resize(img, (400, int(400 * h / w))), [cv2.IMWRITE_JPEG_QUALITY, 75])
        path = tp
    headers = {"Cache-Control": "private, max-age=86400"}
    if download:
        return FileResponse(path, media_type="image/jpeg", filename=path.name, headers=headers)
    return FileResponse(path, media_type="image/jpeg", headers=headers)


@app.post("/api/snapshots/capture")
def capture(user=User):
    snap = engine.manual_snapshot()
    if not snap:
        raise HTTPException(503, "Camera not available")
    return snap


def _del_snap(s):
    delete_snapshot(s)
    p = Path(s["path"])
    for extra in (p.with_name(p.stem + "_thumb.jpg"),):
        extra.unlink(missing_ok=True)
    if s.get("annotated_path"):
        a = Path(s["annotated_path"])
        a.with_name(a.stem + "_thumb.jpg").unlink(missing_ok=True)


@app.delete("/api/snapshots/{sid}")
def del_snapshot(sid: int, user=User):
    _del_snap(_snap(sid))
    return {"ok": True}


@app.post("/api/snapshots/delete")
def del_snapshots(payload: dict = Body(...), user=User):
    n = 0
    for sid in payload.get("ids", []):
        s = db.one("SELECT * FROM snapshots WHERE id=?", (int(sid),))
        if s:
            _del_snap(s)
            n += 1
    log.info("Deleted %d snapshots", n)
    return {"deleted": n}


# ====================== RECORDINGS ======================
@app.get("/api/recordings")
def list_recordings(kind: str | None = None, start: float | None = None, end: float | None = None,
                    limit: int = Query(50, le=500), offset: int = 0, user=User):
    where, params = [], []
    if kind:
        where.append("kind=?")
        params.append(kind)
    _range_filters(where, params, "started_at", start, end)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.one(f"SELECT COUNT(*) c FROM recordings {w}", params)["c"]
    rows = db.query(f"SELECT id, kind, event_id, path, started_at, ended_at, duration, size, status FROM recordings {w} ORDER BY started_at DESC LIMIT ? OFFSET ?", params + [limit, offset])
    for r in rows:
        r["filename"] = Path(r.pop("path")).name
    return {"total": total, "items": rows}


def _rec(rid: int) -> dict:
    r = db.one("SELECT * FROM recordings WHERE id=?", (rid,))
    if not r:
        raise HTTPException(404, "Recording not found")
    return r


def _range_file(request: Request, path: Path, media_type: str, filename: str | None = None):
    size = path.stat().st_size
    rng = request.headers.get("range")
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    if not rng:
        return FileResponse(path, media_type=media_type, headers=headers)
    m = re.match(r"bytes=(\d*)-(\d*)", rng)
    if not m:
        raise HTTPException(416, "Bad range")
    start = int(m.group(1)) if m.group(1) else max(0, size - int(m.group(2) or 0))
    end = int(m.group(2)) if m.group(1) and m.group(2) else size - 1
    end = min(end, size - 1)
    if start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    length = end - start + 1

    def it():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1 << 16, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(length)})
    return StreamingResponse(it(), status_code=206, media_type=media_type, headers=headers)


@app.get("/api/recordings/{rid}/video")
def recording_video(rid: int, request: Request, download: int = 0, user=User):
    r = _rec(rid)
    p = Path(r["path"])
    if r["status"] == "recording":
        raise HTTPException(409, "Recording still in progress")
    if not p.exists():
        raise HTTPException(404, "File missing")
    return _range_file(request, p, "video/mp4", p.name if download else None)


@app.get("/api/recordings/{rid}/thumb")
def recording_thumb(rid: int, user=User):
    r = _rec(rid)
    if not r["thumb_path"] or not Path(r["thumb_path"]).exists():
        raise HTTPException(404, "No thumbnail")
    return FileResponse(r["thumb_path"], media_type="image/jpeg")


@app.delete("/api/recordings/{rid}")
def del_recording(rid: int, user=User):
    r = _rec(rid)
    if r["status"] == "recording":
        raise HTTPException(409, "Recording in progress — stop it first")
    delete_recording(r)
    return {"ok": True}


@app.post("/api/recordings/delete")
def del_recordings(payload: dict = Body(...), user=User):
    n = 0
    for rid in payload.get("ids", []):
        r = db.one("SELECT * FROM recordings WHERE id=?", (int(rid),))
        if r and r["status"] != "recording":
            delete_recording(r)
            n += 1
    log.info("Deleted %d recordings", n)
    return {"deleted": n}


# ====================== EXPORT ======================
@app.post("/api/export")
def export(payload: dict = Body(...), user=User):
    snaps = [db.one("SELECT * FROM snapshots WHERE id=?", (int(i),)) for i in payload.get("snapshot_ids", [])]
    recs = [db.one("SELECT * FROM recordings WHERE id=?", (int(i),)) for i in payload.get("recording_ids", [])]
    for eid in payload.get("event_ids", []):
        snaps += db.query("SELECT * FROM snapshots WHERE event_id=?", (int(eid),))
        recs += db.query("SELECT * FROM recordings WHERE event_id=? AND status='complete'", (int(eid),))
    files = []
    for s in filter(None, snaps):
        files.append((s["path"], "snapshots/" + Path(s["path"]).name))
        if s.get("annotated_path"):
            files.append((s["annotated_path"], "snapshots/" + Path(s["annotated_path"]).name))
    for r in filter(None, recs):
        if r["status"] == "complete":
            files.append((r["path"], f"recordings/{r['kind']}/" + Path(r["path"]).name))
    files = [(a, b) for a, b in dict.fromkeys(files) if Path(a).exists()]
    if not files:
        raise HTTPException(400, "Nothing to export")
    name = datetime.now().strftime("cctv_export_%Y%m%d_%H%M%S.zip")
    out = EXPORT_DIR / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for src, arc in files:
            z.write(src, arc)
    log.info("Export created: %s (%d files)", name, len(files))
    return {"url": f"/api/export/{name}", "files": len(files), "size": out.stat().st_size}


@app.get("/api/export/{name}")
def get_export(name: str, user=User):
    if not re.fullmatch(r"cctv_export_\d{8}_\d{6}\.zip", name):
        raise HTTPException(400, "Bad name")
    p = EXPORT_DIR / name
    if not p.exists():
        raise HTTPException(404, "Export expired")
    return FileResponse(p, media_type="application/zip", filename=name)


# ====================== SETTINGS / CAMERA / RECORDING CONTROL ======================
@app.get("/api/settings")
def get_settings(user=User):
    return settings.all(masked=True)


@app.put("/api/settings/{section}")
def put_settings(section: str, payload: dict = Body(...), user=User):
    if section not in ("camera", "detection", "recording", "storage", "notifications", "server"):
        raise HTTPException(404, "Unknown section")
    if section == "server":
        payload = {k: v for k, v in payload.items() if k in ("host", "session_hours")}
        if payload.get("host") not in (None, "127.0.0.1", "0.0.0.0"):
            raise HTTPException(400, "host must be 127.0.0.1 (local only) or 0.0.0.0 (LAN)")
    old_cam = settings.section("camera")
    try:
        res = settings.update(section, payload)
    except KeyError:
        raise HTTPException(404, "Unknown section")
    if section == "camera":
        keys = ("source", "width", "height", "fps")
        if any(old_cam.get(k) != res.get(k) for k in keys):
            camera.restart()
    if section == "recording" and "paused" in payload:
        log.warning("Privacy pause %s", "ENABLED" if payload["paused"] else "disabled")
    log.info("Settings updated: %s", section)
    return res


@app.get("/api/cameras")
def cameras(user=User):
    found = probe_cameras() if not camera.connected else []
    from .camera import list_camera_names
    names = list_camera_names()
    if camera.connected:  # don't steal the open device; list names instead
        found = [{"index": c["index"], "name": c["name"]} for c in names]
    return {"cameras": found, "active": camera.status()}


@app.post("/api/camera/reconnect")
def camera_reconnect(user=User):
    camera.restart()
    log.info("Camera reconnect requested")
    return {"ok": True}


@app.post("/api/recording/control")
def recording_control(payload: dict = Body(...), user=User):
    allowed = {k: bool(v) for k, v in payload.items() if k in ("paused", "continuous_enabled", "event_enabled")}
    if not allowed:
        raise HTTPException(400, "Nothing to change")
    settings.update("recording", allowed)
    log.info("Recording control: %s", allowed)
    return recorder.status() | allowed


@app.get("/api/models")
def models(user=User):
    out = []
    for m in MODELS:
        out.append(m | {"downloaded": (MODELS_DIR / m["file"]).exists()})
    return {"models": out, "active": detector.info(), "recommended": recommended_model(), "hardware": hardware_info()}


@app.post("/api/models/zones")
def save_zones(payload: dict = Body(...), user=User):
    zones = payload.get("zones", [])
    clean = []
    for i, z in enumerate(zones):
        pts = [[min(max(float(p[0]), 0), 1), min(max(float(p[1]), 0), 1)] for p in z.get("points", [])]
        if len(pts) >= 3:
            clean.append({"id": z.get("id") or f"z{i}", "name": str(z.get("name") or f"Zone {i + 1}")[:40],
                          "type": "ignore" if z.get("type") == "ignore" else "detect", "points": pts,
                          "enabled": bool(z.get("enabled", True))})
    settings.update("detection", {"zones": clean})
    return {"zones": clean}


# ====================== NOTIFICATIONS ======================
@app.get("/api/notifications")
def notifications(limit: int = Query(100, le=500), offset: int = 0, user=User):
    total = db.one("SELECT COUNT(*) c FROM notifications")["c"]
    return {"total": total, "items": db.query("SELECT * FROM notifications ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)),
            "status": notifier.status()}


@app.post("/api/notifications/test/{channel}")
def test_notification(channel: str, user=User):
    if channel not in CHANNELS:
        raise HTTPException(404, "Unknown channel")
    res = notifier.test(channel)
    if res["status"] != "sent":
        raise HTTPException(400, res.get("error") or "Failed")
    return res


# ====================== STORAGE / LOGS ======================
@app.get("/api/storage")
def storage_stats(user=User):
    return storage.stats(fresh=True)


@app.post("/api/storage/cleanup")
def storage_cleanup(user=User):
    return {"removed": storage.cleanup(), "stats": storage.stats(fresh=True)}


@app.get("/api/logs")
def logs(level: str | None = None, since: int = 0, search: str | None = None, limit: int = Query(500, le=3000), user=User):
    return {"items": get_logs(level, since, limit, search)}


@app.get("/api/logs/download")
def logs_download(user=User):
    return FileResponse(LOG_FILE, media_type="text/plain", filename="cctv.log")


# ====================== FRONTEND ======================
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(404, "Not found")
    f = (FRONTEND_DIST / full_path).resolve()
    if full_path and f.is_file() and FRONTEND_DIST.resolve() in f.parents:
        return FileResponse(f, media_type=mimetypes.guess_type(str(f))[0])
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        return Response("Frontend not built. Run ./install.sh", media_type="text/plain", status_code=503)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})


def run():
    import uvicorn
    host = os.environ.get("CCTV_HOST") or settings.get("server.host", "127.0.0.1")
    port = int(os.environ.get("CCTV_PORT") or settings.get("server.port", 8090))
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    run()
