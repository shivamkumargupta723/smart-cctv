"""System / hardware information and aggregated status."""
from __future__ import annotations

import platform
import subprocess
import time
from functools import lru_cache

import psutil

from .logs import uptime_start


@lru_cache(maxsize=1)
def hardware_info() -> dict:
    chip = platform.processor() or platform.machine()
    if platform.system() == "Darwin":
        try:
            chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, timeout=5).stdout.strip() or chip
        except Exception:
            pass
        mac_ver = platform.mac_ver()[0]
        os_name = f"macOS {mac_ver}"
    else:
        os_name = f"{platform.system()} {platform.release()}"
    accel = "cpu"
    try:
        import torch
        if torch.backends.mps.is_available():
            accel = "mps (Apple Silicon GPU)"
        elif torch.cuda.is_available():
            accel = f"cuda ({torch.cuda.get_device_name(0)})"
    except Exception:
        pass
    return {
        "os": os_name, "arch": platform.machine(), "chip": chip, "cpu_cores": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 1e9, 1), "python": platform.python_version(), "accelerator": accel,
        "apple_silicon": platform.system() == "Darwin" and platform.machine() == "arm64",
    }


def recommended_model() -> str:
    hw = hardware_info()
    if hw["apple_silicon"] and hw["ram_gb"] >= 15:
        return "yolo11s.pt"
    return "yolo11n.pt"


def system_status() -> dict:
    from .camera import camera
    from .detector import detector
    from .engine import engine
    from .notifier import notifier
    from .recorder import recorder
    from .storage import storage

    st = storage.stats()
    return {
        "ts": time.time(),
        "uptime": time.time() - uptime_start(),
        "camera": camera.status(),
        "recording": recorder.status(),
        "detector": detector.info(),
        "engine": {k: v for k, v in engine.status().items() if k != "detections"} | {"stream_fps": round(engine.stream_fps, 1)},
        "storage": {k: st[k] for k in ("disk_total", "disk_free", "disk_used", "percent_used", "cctv_total", "low")},
        "notifications": notifier.status()["channels"],
        "cpu_percent": psutil.cpu_percent(interval=None),
        "mem_percent": psutil.virtual_memory().percent,
    }
