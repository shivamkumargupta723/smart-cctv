"""Inspect OS, processor, memory, accelerator and connected cameras; recommend a YOLO model.

Usage: python scripts/system_check.py [--write-config]
"""
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from backend.app.system import hardware_info, recommended_model
    from backend.app.camera import list_camera_names, probe_cameras

    hw = hardware_info()
    print("=" * 60)
    print(" Smart CCTV — system check")
    print("=" * 60)
    for k in ("os", "arch", "chip", "cpu_cores", "ram_gb", "accelerator", "python"):
        print(f"  {k:<12}: {hw[k]}")
    if platform.system() == "Darwin":
        try:
            out = subprocess.run(["system_profiler", "SPCameraDataType"], capture_output=True, text=True, timeout=20).stdout
            names = [l.strip().rstrip(":") for l in out.splitlines() if l.startswith("    ") and l.strip().endswith(":")]
            print(f"  {'cameras(OS)':<12}: {', '.join(names) or 'none reported'}")
        except Exception:
            pass
    listed = list_camera_names()
    if listed:
        print("  Video devices:")
        for c in listed:
            print(f"    [{c['index']}] {c['name']}")
    print("  Testing camera access (macOS may ask for Camera permission) ...")
    cams = probe_cameras()
    if cams:
        for c in cams:
            print(f"    OK  [{c['index']}] {c['name']}  {c['width']}x{c['height']}")
    else:
        print("    !! No camera could be opened. Plug in the USB webcam and allow Camera access")
        print("       for Terminal: System Settings > Privacy & Security > Camera.")
    model = recommended_model()
    print(f"  Recommended AI model: {model}")
    report = {"hardware": hw, "cameras": cams, "recommended_model": model}
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "logs" / "system_check.json").write_text(json.dumps(report, indent=2))
    if "--write-config" in sys.argv:
        from backend.app.config import settings
        if settings.get("detection.model") in (None, "", "yolo11n.pt"):
            settings.update("detection", {"model": model})
        print(f"  Saved model choice to config/settings.json -> {settings.get('detection.model')}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
