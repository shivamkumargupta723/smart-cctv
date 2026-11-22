<div align="center">

# 🛡️ Smart CCTV

**Turn any USB webcam into a private, AI-powered security camera that runs 100% locally on your Mac.**

Real-time YOLO11 person / vehicle / animal / object detection · face detection · motion detection ·
automatic photos · 24/7 + smart event recording · instant alerts (Telegram, mobile push, WhatsApp, email, browser)

![Platform](https://img.shields.io/badge/platform-macOS%20(Apple%20Silicon%20%26%20Intel)-black)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![AI](https://img.shields.io/badge/AI-YOLO11%20%2B%20Apple%20MPS-orange)
![Privacy](https://img.shields.io/badge/cloud-none%20by%20default-brightgreen)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

</div>

---

## ✨ Why Smart CCTV?

- **Private by design.** Video, photos and history never leave your computer. There is no account, no subscription and no cloud.
- **Smart, not noisy.** It tells a *person* apart from ordinary motion (curtains, light changes, pets), so you get far fewer false alerts.
- **Fast on Apple Silicon.** AI inference runs on the M-series GPU (MPS). On an M5, YOLO11s runs in real time.
- **One command to install, one command to start.** The dashboard opens at `http://localhost:8090`.

## 📸 Screenshots

> Add your own screenshots to `docs/screenshots/` (see [GITHUB_SETUP.md](GITHUB_SETUP.md)).

| Live camera | Event history | Recordings |
|---|---|---|
| ![Live](docs/screenshots/live.png) | ![Events](docs/screenshots/events.png) | ![Recordings](docs/screenshots/recordings.png) |

## 🚀 Features

| Area | What you get |
|---|---|
| **AI detection** | YOLO11 (80 COCO classes): people, vehicles, animals, everyday objects · YuNet face detection (location only, **no identity recognition**) · motion detection · multi-person count |
| **Smart presence** | Person tracking with IDs · **entry / exit** events with dwell time · **loitering** alert · N-frame confirmation against false positives |
| **Zones** | Draw polygon **detection zones** (door, gate) and **ignore zones** (TV, trees, road) right on the live image |
| **Day / night** | Automatic switching by brightness · separate night threshold · CLAHE low-light enhancement |
| **Photos** | High-quality JPEG plus an AI-annotated copy, timestamped · no duplicate floods (interval + per-event limit) |
| **Recording** | **Continuous 24/7** in segments · **smart event clips** with pre-event buffer and post-event tail · browser-playable H.264 MP4 |
| **Alerts** | Browser · mobile push via **ntfy** · **Telegram** · **WhatsApp Business Cloud API** · **Email (SMTP)**, all with photo and timestamp · cooldown against spam |
| **Triggers** | Person enters · person stays · motion · selected objects · camera disconnected · low storage |
| **Dashboard** | Live view, AI detection, event history (search + filters), photo gallery, video recordings, notifications, camera settings, AI model settings, storage, system logs |
| **Storage** | Per-type retention · automatic hourly cleanup · minimum-free-space guard · ZIP export |
| **Security** | Login required · PBKDF2 password hashing · HttpOnly cookies · login rate limit · secrets encrypted at rest · localhost-only by default · **privacy pause** (camera fully off) |

## ⚡ Quick start

```bash
git clone https://github.com/<your-username>/smart-cctv.git
cd smart-cctv
./install.sh     # checks hardware & webcam, installs everything, downloads AI models
./start.sh       # opens http://localhost:8090
```

1. Allow **Camera** access for Terminal when macOS asks. You can change this later in System Settings → Privacy & Security → Camera.
2. Create your admin account on the first visit.
3. Plug in your USB webcam. It is selected automatically. Otherwise, pick it under *Camera Settings → Scan*.

### Requirements
- macOS 12+ on Apple Silicon (M1–M5) or Intel
- Python 3.10+ (the installer installs it through Homebrew if missing)
- ~3 GB of disk for the software, plus space for recordings
- [Homebrew](https://brew.sh) is recommended

### Everyday commands

| Command | Purpose |
|---|---|
| `./start.sh` | Start and open the dashboard (Ctrl+C stops it) |
| `./stop.sh` | Stop (also stops the autostart service) |
| `./scripts/install-autostart.sh` | Start automatically at login and restart after a crash |
| `./scripts/uninstall-autostart.sh` | Remove autostart |
| `./scripts/reset-password.sh` | Reset the dashboard password |
| `.venv/bin/python scripts/system_check.py` | Show hardware and detected webcams |

## 🔔 Setting up alerts

| Channel | How |
|---|---|
| **Browser** | Notifications → *Allow notifications* |
| **Mobile push (ntfy)** | Install the ntfy app, subscribe to a long random topic, and enter the same topic in the dashboard |
| **Telegram** | Use [@BotFather](https://t.me/BotFather) to run `/newbot` and copy the token. Message your bot, open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id` |
| **WhatsApp** | Meta developer app → WhatsApp Cloud API → Phone number ID and permanent token. Free-form messages are only delivered within 24 h of the recipient messaging your number. |
| **Email** | Any SMTP server. For Gmail, use an App Password on port 587. |

Every channel has a **Test** button, and every send is logged with its error, if any.

## 🧠 How it works

```
USB webcam ──► Camera thread (AVFoundation, auto-reconnect)
                 │
                 ├──► AI engine: YOLO11 (MPS) + YuNet faces + MOG2 motion + zones + tracker
                 │        └──► Events ─► Photos ─► Alerts (ntfy / Telegram / WhatsApp / Email / Browser)
                 │
                 ├──► Recorder: pre-event RAM buffer → ffmpeg H.264 (event clips + 24/7 segments)
                 │
                 └──► MJPEG live stream + WebSocket ─► React dashboard (localhost:8090)
                                                       SQLite: events · photos · recordings · alerts
```

## 🗂️ Project structure

```
smart-cctv/
├── backend/app/          FastAPI server (camera, detector, engine, recorder, notifier, storage, auth)
├── frontend/             React + TypeScript + Tailwind (src/ and prebuilt dist/)
├── scripts/              system check, model download, autostart, password reset
├── models/               YOLO + face models
├── database/             SQLite (created at install)
├── recordings/           continuous/ and events/ (per day)
├── snapshots/            photos (per day)
├── logs/                 rotating application logs
├── config/               settings.json + encryption key (never commit these)
├── install.sh · start.sh · stop.sh
└── requirements.txt
```

## 🛠️ Development

```bash
source .venv/bin/activate && python -m backend.app.main    # API + dashboard on :8090
cd frontend && npm install && npm run dev                   # hot-reload UI on :5173 (proxies to :8090)
npm run build                                               # rebuild frontend/dist
```

**Tech stack:** Python · FastAPI · OpenCV · Ultralytics YOLO11 · PyTorch (MPS) · FFmpeg · SQLite · WebSockets · React · TypeScript · Tailwind CSS · Vite

## 🔒 Privacy, security & legal

- Nothing is uploaded by default. Only the alert channels **you** enable send an alert text and one photo.
- The server listens on `127.0.0.1` only. LAN access is an explicit opt-in. **Never expose port 8090 directly to the internet.**
- Tokens and passwords are encrypted at rest (Fernet), and the API never sends them back to the browser.
- A red **REC** indicator is always visible while recording. Privacy pause turns the camera fully off.
- **Use responsibly:** only monitor places you are authorized to monitor. Inform people where required, and follow local privacy and CCTV laws (e.g. India's DPDP Act 2023, GDPR in the EU). This software does not perform face *recognition*.

## 🩺 Troubleshooting

| Problem | Fix |
|---|---|
| Camera offline | Allow Camera access for Terminal · close Zoom/FaceTime · *Camera Settings → Scan → select → Reconnect* |
| Works with `start.sh` but not with autostart | Enable `python3` under Privacy & Security → Camera |
| High CPU | Lower *Max AI fps* or *Inference resolution*, or switch to YOLO11n |
| Too many alerts | Raise the confidence threshold, add ignore zones, increase the cooldown |
| Recordings won't play | `brew install ffmpeg`, then restart |
| Port busy | `CCTV_PORT=8091 ./start.sh` |

Logs: dashboard → **System Logs**, or `logs/cctv.log`.

## 🤝 Contributing

Issues and pull requests are welcome. Please don't attach recordings or photos of real people to issues.

## 📄 License

[MIT](LICENSE) © 2026 Shivam Kumar Gupta

YOLO11 models are provided by [Ultralytics](https://github.com/ultralytics/ultralytics) under AGPL-3.0. Review their license before any commercial use.
