"""Download AI models into models/: YOLO11 (Ultralytics) + YuNet face detector + Haar fallback."""
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
MODELS.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))

FILES = {
    "face_detection_yunet_2023mar.onnx": "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "haarcascade_frontalface_default.xml": "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_frontalface_default.xml",
}


def fetch(name, url, min_size):
    dest = MODELS / name
    if dest.exists() and dest.stat().st_size >= min_size:
        print(f"  ✓ {name} (already present)")
        return True
    try:
        print(f"  ↓ {name} ...")
        tmp = dest.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        if tmp.stat().st_size < min_size:
            raise RuntimeError("downloaded file too small")
        tmp.replace(dest)
        print(f"  ✓ {name}")
        return True
    except Exception as e:
        print(f"  ! could not download {name}: {e}")
        return False


def main():
    from backend.app.config import settings
    yolo = [settings.get("detection.model", "yolo11n.pt")]
    if "yolo11n.pt" not in yolo:
        yolo.append("yolo11n.pt")  # small fallback model
    from ultralytics import YOLO
    import os
    os.chdir(MODELS)
    for m in yolo:
        if (MODELS / m).exists():
            print(f"  ✓ {m} (already present)")
            continue
        print(f"  ↓ {m} ...")
        YOLO(m)  # Ultralytics downloads into the current directory (models/)
        print(f"  ✓ {m}")
    for name, url in FILES.items():
        fetch(name, url, 100_000)


if __name__ == "__main__":
    main()
