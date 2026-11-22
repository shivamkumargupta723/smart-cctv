"""AI detection: YOLO objects, OpenCV faces, motion, zones and person tracking."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import cv2
import numpy as np

from .config import MODELS_DIR, settings

log = logging.getLogger("detector")

VEHICLES = {"bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"}
ANIMALS = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}
COLORS = {"person": (0, 200, 255), "vehicle": (255, 140, 0), "animal": (80, 220, 80), "object": (220, 120, 255), "face": (255, 255, 0)}


def category_of(label: str) -> str:
    if label == "person":
        return "person"
    if label in VEHICLES:
        return "vehicle"
    if label in ANIMALS:
        return "animal"
    return "object"


@dataclass
class Detection:
    label: str
    category: str
    confidence: float
    box: tuple[int, int, int, int]  # x1,y1,x2,y2 pixels
    track_id: int | None = None

    def to_dict(self, w: int, h: int):
        x1, y1, x2, y2 = self.box
        return {
            "label": self.label, "category": self.category, "confidence": round(self.confidence, 3),
            "box": [x1 / w, y1 / h, x2 / w, y2 / h], "track_id": self.track_id,
        }


@dataclass
class Track:
    id: int
    box: tuple
    first_seen: float
    last_seen: float
    hits: int = 1
    confirmed: bool = False
    loiter_alerted: bool = False
    confidence: float = 0.0


@dataclass
class FrameResult:
    ts: float
    width: int
    height: int
    detections: list[Detection] = field(default_factory=list)
    motion: bool = False
    motion_ratio: float = 0.0
    motion_boxes: list = field(default_factory=list)
    persons: int = 0
    night: bool = False
    brightness: float = 0.0
    entered: list[Track] = field(default_factory=list)
    exited: list[Track] = field(default_factory=list)
    loitering: list[Track] = field(default_factory=list)
    inference_ms: float = 0.0


def _iou(a, b) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


class PersonTracker:
    """IoU + centroid tracker producing entry / exit / loitering events."""

    def __init__(self):
        self.tracks: dict[int, Track] = {}
        self._next = 1

    def reset(self):
        self.tracks.clear()

    def update(self, persons: list[Detection], now: float, frame_diag: float):
        cfg = settings.section("detection")
        confirm = int(cfg.get("person_confirm_frames", 2))
        timeout = float(cfg.get("exit_timeout_seconds", 3.0))
        loiter = float(cfg.get("loiter_seconds", 30))
        entered, exited, loitering = [], [], []
        unmatched = set(self.tracks.keys())
        for det in sorted(persons, key=lambda d: -d.confidence):
            best, best_score = None, 0.0
            for tid in unmatched:
                t = self.tracks[tid]
                score = _iou(t.box, det.box)
                if score < 0.15:
                    cx1, cy1 = (t.box[0] + t.box[2]) / 2, (t.box[1] + t.box[3]) / 2
                    cx2, cy2 = (det.box[0] + det.box[2]) / 2, (det.box[1] + det.box[3]) / 2
                    dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5 / max(frame_diag, 1)
                    score = max(0.0, 0.3 - dist) if dist < 0.15 else 0.0
                if score > best_score:
                    best, best_score = tid, score
            if best is not None:
                t = self.tracks[best]
                t.box, t.last_seen, t.confidence = det.box, now, det.confidence
                t.hits += 1
                unmatched.discard(best)
            else:
                t = Track(self._next, det.box, now, now, confidence=det.confidence)
                self.tracks[t.id] = t
                self._next += 1
            det.track_id = t.id
            if not t.confirmed and t.hits >= confirm:
                t.confirmed = True
                entered.append(t)
            if t.confirmed and not t.loiter_alerted and now - t.first_seen >= loiter:
                t.loiter_alerted = True
                loitering.append(t)
        for tid in list(self.tracks.keys()):
            t = self.tracks[tid]
            if now - t.last_seen > timeout:
                if t.confirmed:
                    exited.append(t)
                del self.tracks[tid]
        active = sum(1 for t in self.tracks.values() if t.confirmed and now - t.last_seen < 1.0)
        return active, entered, exited, loitering


class Detector:
    def __init__(self):
        self._lock = threading.Lock()
        self.model = None
        self.model_name = ""
        self.device = "cpu"
        self.load_error = ""
        self.names: dict[int, str] = {}
        self._bg = None
        self._bg_sens = None
        self.tracker = PersonTracker()
        self._face = None
        self._face_kind = ""
        self._mask_cache = {}
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        settings.on_change(self._on_settings)

    # ---------- model ----------
    def _on_settings(self, section):
        if section == "detection":
            cfg = settings.section("detection")
            if cfg.get("model") != self.model_name or (cfg.get("device") != "auto" and cfg.get("device") != self.device):
                threading.Thread(target=self.load, daemon=True).start()
            self._mask_cache.clear()

    def _pick_device(self, wanted: str) -> str:
        try:
            import torch
            if wanted in ("mps", "auto") and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                return "mps"
            if wanted in ("cuda", "auto") and torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    def load(self):
        cfg = settings.section("detection")
        name = cfg.get("model", "yolo11n.pt")
        path = MODELS_DIR / name
        try:
            from ultralytics import YOLO
            log.info("Loading YOLO model %s ...", name)
            model = YOLO(str(path) if path.exists() else name)
            if not path.exists():
                # ultralytics downloads to CWD; move it into models/
                import shutil
                from pathlib import Path
                if Path(name).exists():
                    shutil.move(name, path)
            device = self._pick_device(cfg.get("device", "auto"))
            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            try:
                model.predict(dummy, device=device, verbose=False, imgsz=int(cfg.get("imgsz", 640)))
            except Exception as e:
                log.warning("Device %s failed (%s); falling back to CPU", device, e)
                device = "cpu"
                model.predict(dummy, device=device, verbose=False)
            with self._lock:
                self.model, self.model_name, self.device = model, name, device
                self.names = model.names
                self.load_error = ""
            log.info("YOLO model %s ready on %s (%d classes)", name, device, len(self.names))
        except Exception as e:
            self.load_error = str(e)
            log.exception("Failed to load YOLO model %s", name)
        self._load_face()

    def _load_face(self):
        if self._face is not None:
            return
        yunet = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
        if yunet.exists() and hasattr(cv2, "FaceDetectorYN"):
            try:
                self._face = cv2.FaceDetectorYN.create(str(yunet), "", (320, 320), 0.7, 0.3, 50)
                self._face_kind = "yunet"
                log.info("Face detector: YuNet (DNN)")
                return
            except Exception as e:
                log.warning("YuNet unavailable: %s", e)
        try:
            import os
            path = str(MODELS_DIR / "haarcascade_frontalface_default.xml")
            if not os.path.exists(path):
                path = getattr(getattr(cv2, "data", None), "haarcascades", "") + "haarcascade_frontalface_default.xml"
            if not os.path.exists(path):
                log.warning("No face model found in models/ — run ./install.sh to download it")
                return
            c = cv2.CascadeClassifier(path)
            if not c.empty():
                self._face = c
                self._face_kind = "haar"
                log.info("Face detector: Haar cascade")
        except Exception as e:
            log.warning("No face detector available: %s", e)

    def info(self) -> dict:
        return {
            "model": self.model_name, "device": self.device, "loaded": self.model is not None,
            "error": self.load_error, "face_detector": self._face_kind, "classes": list(self.names.values()),
        }

    # ---------- zones ----------
    def _zone_masks(self, w: int, h: int):
        key = (w, h)
        if key in self._mask_cache:
            return self._mask_cache[key]
        zones = settings.get("detection.zones", []) or []
        detect = np.zeros((h, w), np.uint8)
        ignore = np.zeros((h, w), np.uint8)
        has_detect = False
        for z in zones:
            pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in z.get("points", [])], np.int32)
            if len(pts) < 3 or not z.get("enabled", True):
                continue
            if z.get("type") == "ignore":
                cv2.fillPoly(ignore, [pts], 255)
            else:
                cv2.fillPoly(detect, [pts], 255)
                has_detect = True
        res = (detect if has_detect else None, ignore if ignore.any() else None)
        self._mask_cache[key] = res
        return res

    @staticmethod
    def _point_in(mask, x, y) -> bool:
        h, w = mask.shape
        return mask[min(max(int(y), 0), h - 1), min(max(int(x), 0), w - 1)] > 0

    def _zone_ok(self, box, masks) -> bool:
        detect, ignore = masks
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        foot_y = box[3] - 2
        if ignore is not None and self._point_in(ignore, cx, cy):
            return False
        if detect is not None and not (self._point_in(detect, cx, foot_y) or self._point_in(detect, cx, cy)):
            return False
        return True

    # ---------- main ----------
    def process(self, frame: np.ndarray) -> FrameResult:
        cfg = settings.section("detection")
        h, w = frame.shape[:2]
        now = time.time()
        res = FrameResult(ts=now, width=w, height=h)
        masks = self._zone_masks(w, h)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        res.brightness = float(gray.mean())
        mode = cfg.get("night_mode", "auto")
        res.night = mode == "night" or (mode == "auto" and res.brightness < float(cfg.get("night_brightness_threshold", 60)))

        work = frame
        if res.night and cfg.get("night_enhance", True):
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            lab[:, :, 0] = self._clahe.apply(lab[:, :, 0])
            work = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        # Motion
        if cfg.get("motion_enabled", True):
            res.motion, res.motion_ratio, res.motion_boxes = self._motion(gray, masks, cfg)

        if not cfg.get("enabled", True) or self.model is None:
            return res

        person_conf = float(cfg.get("night_person_confidence" if res.night else "person_confidence", 0.5))
        obj_conf = float(cfg.get("object_confidence", 0.45))
        t0 = time.time()
        with self._lock:
            model, device = self.model, self.device
        try:
            r = model.predict(work, conf=min(person_conf, obj_conf), device=device, verbose=False,
                              imgsz=int(cfg.get("imgsz", 640)))[0]
        except Exception as e:
            log.error("Inference failed: %s", e)
            return res
        res.inference_ms = (time.time() - t0) * 1000
        persons = []
        if r.boxes is not None and len(r.boxes):
            xyxy = r.boxes.xyxy.cpu().numpy().astype(int)
            confs = r.boxes.conf.cpu().numpy()
            clss = r.boxes.cls.cpu().numpy().astype(int)
            for box, c, k in zip(xyxy, confs, clss):
                label = self.names.get(int(k), str(k))
                cat = category_of(label)
                if cat == "person":
                    if not cfg.get("detect_persons", True) or c < person_conf:
                        continue
                elif c < obj_conf or not cfg.get(f"detect_{cat}s" if cat != "object" else "detect_objects", True):
                    continue
                b = tuple(int(v) for v in box)
                if not self._zone_ok(b, masks):
                    continue
                d = Detection(label, cat, float(c), b)
                res.detections.append(d)
                if cat == "person":
                    persons.append(d)

        diag = (w * w + h * h) ** 0.5
        res.persons, res.entered, res.exited, res.loitering = self.tracker.update(persons, now, diag)

        if cfg.get("detect_faces", True) and self._face is not None and persons:
            res.detections.extend(self._faces(frame, persons))
        return res

    def _motion(self, gray, masks, cfg):
        sens = int(cfg.get("motion_sensitivity", 50))
        if self._bg is None or self._bg_sens != sens:
            var = float(np.interp(sens, [1, 100], [80, 8]))
            self._bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=var, detectShadows=False)
            self._bg_sens = sens
        small = cv2.resize(gray, (320, int(320 * gray.shape[0] / gray.shape[1])))
        small = cv2.GaussianBlur(small, (5, 5), 0)
        fg = self._bg.apply(small)
        _, fg = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        fg = cv2.dilate(fg, np.ones((5, 5), np.uint8), iterations=2)
        detect, ignore = masks
        sh, sw = fg.shape
        if ignore is not None:
            fg[cv2.resize(ignore, (sw, sh)) > 0] = 0
        if detect is not None:
            fg[cv2.resize(detect, (sw, sh)) == 0] = 0
        ratio = float(np.count_nonzero(fg)) / fg.size
        min_area = float(cfg.get("motion_min_area", 0.005))
        boxes = []
        if ratio >= min_area:
            cnts, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                if cv2.contourArea(c) >= min_area * fg.size * 0.3:
                    x, y, bw, bh = cv2.boundingRect(c)
                    boxes.append([x / sw, y / sh, (x + bw) / sw, (y + bh) / sh])
        # A global lighting change lights up most of the frame -> not real motion
        motion = bool(boxes) and ratio < 0.6
        return motion, ratio, boxes

    def _faces(self, frame, persons):
        faces = []
        h, w = frame.shape[:2]
        for p in persons:
            x1, y1, x2, y2 = p.box
            ph = y2 - y1
            # Faces are in the upper part of a person box
            ry2 = y1 + max(int(ph * 0.6), 1)
            roi = frame[max(y1, 0):min(ry2, h), max(x1, 0):min(x2, w)]
            if roi.size == 0 or roi.shape[0] < 24 or roi.shape[1] < 24:
                continue
            try:
                if self._face_kind == "yunet":
                    self._face.setInputSize((roi.shape[1], roi.shape[0]))
                    _, out = self._face.detect(roi)
                    rects = [] if out is None else [(int(f[0]), int(f[1]), int(f[2]), int(f[3]), float(f[14])) for f in out]
                else:
                    g = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                    min_sz = max(20, roi.shape[1] // 8)
                    rects = [(int(a), int(b), int(c), int(d), 0.8) for a, b, c, d in
                             self._face.detectMultiScale(g, 1.1, 5, minSize=(min_sz, min_sz))]
                for fx, fy, fw, fh, sc in rects[:2]:
                    faces.append(Detection("face", "face", sc, (x1 + fx, y1 + fy, x1 + fx + fw, y1 + fy + fh), p.track_id))
            except Exception:
                continue
        return faces


def annotate(frame: np.ndarray, res: FrameResult | None, draw_zones: bool = True) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]
    scale = max(0.5, w / 1280)
    if draw_zones:
        for z in settings.get("detection.zones", []) or []:
            pts = np.array([[int(p[0] * w), int(p[1] * h)] for p in z.get("points", [])], np.int32)
            if len(pts) < 3 or not z.get("enabled", True):
                continue
            color = (60, 60, 230) if z.get("type") == "ignore" else (60, 200, 60)
            overlay = out.copy()
            cv2.fillPoly(overlay, [pts], color)
            cv2.addWeighted(overlay, 0.12, out, 0.88, 0, out)
            cv2.polylines(out, [pts], True, color, max(1, int(2 * scale)))
            cv2.putText(out, z.get("name", ""), tuple(pts[0] + [4, 18]), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * scale, color, 1, cv2.LINE_AA)
    if res is not None and res.width == w:
        for d in res.detections:
            x1, y1, x2, y2 = d.box
            color = COLORS.get(d.category, (255, 255, 255))
            th = max(1, int(2 * scale))
            cv2.rectangle(out, (x1, y1), (x2, y2), color, th)
            txt = f"{d.label} {d.confidence * 100:.0f}%"
            if d.track_id and d.category == "person":
                txt = f"#{d.track_id} " + txt
            (tw, tht), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5 * scale, 1)
            cv2.rectangle(out, (x1, max(0, y1 - tht - 8)), (x1 + tw + 6, y1), color, -1)
            cv2.putText(out, txt, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * scale, (0, 0, 0), 1, cv2.LINE_AA)
    return out


def stamp(frame: np.ndarray, text: str, rec: bool = False) -> np.ndarray:
    h, w = frame.shape[:2]
    scale = max(0.45, w / 1600)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    label = f"{text}  {ts}"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    cv2.rectangle(frame, (8, h - th - 18), (16 + tw, h - 6), (0, 0, 0), -1)
    cv2.putText(frame, label, (12, h - 12), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 1, cv2.LINE_AA)
    if rec:
        cv2.circle(frame, (w - 70, 24), 8, (0, 0, 255), -1)
        cv2.putText(frame, "REC", (w - 56, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
    return frame


detector = Detector()
