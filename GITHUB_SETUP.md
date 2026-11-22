# GitHub pe Smart CCTV launch karne ki guide

## 1. Repository details (copy-paste ke liye)

**Repository name:** `smart-cctv`

**Description (350 characters se kam):**
> Private AI security camera for macOS. Turn any USB webcam into a smart CCTV with YOLO11 person/vehicle/animal detection, face detection, motion alerts, 24/7 + event recording, and Telegram/WhatsApp/email/push notifications. 100% local, no cloud. FastAPI + React.

**Topics:**
`cctv` `security-camera` `surveillance` `yolo` `yolo11` `object-detection` `person-detection` `computer-vision` `opencv` `fastapi` `react` `typescript` `tailwindcss` `macos` `apple-silicon` `webcam` `home-security` `privacy` `telegram-bot` `self-hosted`

**Website:** khaali chhod do (ya baad mein demo video / blog ka link daalo)

---

## 2. Ek command se GitHub pe launch

Yeh command:
1. GitHub CLI (`gh`) install karti hai, agar pehle se nahi hai
2. GitHub login karwati hai (browser khulega, ek baar)
3. Git repo banati hai, files commit karti hai
4. GitHub pe **public** repo `smart-cctv` banati hai aur code push karti hai
5. Description, topics set karti hai aur **v1.0.0 release** banati hai

```bash
cd ~/Downloads/smart-cctv && \
(command -v gh >/dev/null || brew install gh) && \
(gh auth status >/dev/null 2>&1 || gh auth login --web -h github.com -p https) && \
GH_USER=$(gh api user --jq .login) && GH_ID=$(gh api user --jq .id) && \
git init -q -b main 2>/dev/null; \
git config user.name >/dev/null || git config user.name "Shivam Kumar Gupta"; \
git config user.email >/dev/null || git config user.email "${GH_ID}+${GH_USER}@users.noreply.github.com"; \
git add -A && git commit -qm "Smart CCTV v1.0.0 — local AI surveillance for macOS" && \
gh repo create smart-cctv --public --source=. --remote=origin --push \
  --description "Private AI security camera for macOS. Turn any USB webcam into a smart CCTV with YOLO11 person/vehicle/animal detection, face detection, motion alerts, 24/7 + event recording, and Telegram/WhatsApp/email/push notifications. 100% local, no cloud. FastAPI + React." && \
gh repo edit --add-topic cctv,security-camera,surveillance,yolo,yolo11,object-detection,person-detection,computer-vision,opencv,fastapi,react,typescript,tailwindcss,macos,apple-silicon,webcam,home-security,privacy,telegram-bot,self-hosted && \
gh release create v1.0.0 --title "Smart CCTV v1.0.0" --generate-notes && \
open "https://github.com/$GH_USER/smart-cctv"
```

> Repo **private** rakhna ho to `--public` ki jagah `--private` likho.

---

## 3. Screenshots add karna (README mein dikhenge)

1. `./start.sh` chalao, dashboard kholo
2. `Cmd + Shift + 4`, phir `Space` dabao, aur browser window pe click karo. Screenshot Desktop pe save hoga.
3. Teen screenshots lo: **Live Camera**, **Event History**, **Video Recordings**
4. Phir yeh command chalao (Desktop ke latest 3 screenshots copy karke push kar degi):

```bash
cd ~/Downloads/smart-cctv && \
ls -t ~/Desktop/Screenshot*.png | head -3 | { read a; read b; read c; cp "$c" docs/screenshots/live.png; cp "$b" docs/screenshots/events.png; cp "$a" docs/screenshots/recordings.png; } && \
git add docs/screenshots && git commit -qm "Add dashboard screenshots" && git push
```
(Order: sabse pehle Live, phir Events, phir Recordings ka screenshot lena.)

⚠️ **Screenshots mein kisi ka chehra, ghar ka address ya koi token/password nahi dikhna chahiye.** Zaroorat ho to camera ko kisi khaali deewar ki taraf karke screenshot lo.

---

## 4. Baad mein code update karna

```bash
cd ~/Downloads/smart-cctv && git add -A && git commit -m "Describe your change" && git push
```

New version release karne ke liye:
```bash
gh release create v1.1.0 --title "Smart CCTV v1.1.0" --generate-notes
```

---

## 5. Safety checklist (push se pehle)

`.gitignore` yeh sab **automatically GitHub se bahar** rakhta hai:

| Folder / file | Kyun |
|---|---|
| `config/settings.json`, `config/.secret.key` | Telegram/WhatsApp tokens, SMTP password, encryption key |
| `database/` | Events, login sessions, password hash |
| `recordings/`, `snapshots/` | Aapki private video aur photos |
| `logs/`, `exports/` | Private activity data |
| `models/*.pt` | Bade AI model files (install.sh khud download karta hai) |
| `.venv/`, `node_modules/` | Install hone wali libraries |

Push se pehle check karne ke liye:
```bash
git status --short | grep -E "config/|database/|snapshots/|recordings/|\.key|\.db" || echo "✓ Koi private file commit nahi ho rahi"
```

---

## 6. License note

Aapka code **MIT license** mein hai (`LICENSE` file). Ultralytics YOLO **AGPL-3.0** license mein hai. Isliye agar baad mein ise **paid / commercial product** ki tarah bechna ho, to Ultralytics ka Enterprise license lena padega, ya YOLO ki jagah koi aur permissive-license model use karna hoga. Free open-source project ke liye koi dikkat nahi hai.
