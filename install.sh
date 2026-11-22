#!/usr/bin/env bash
# Smart CCTV — one-command installer for macOS (Apple Silicon & Intel)
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
BOLD=$'\e[1m'; GRN=$'\e[32m'; YEL=$'\e[33m'; RED=$'\e[31m'; RST=$'\e[0m'
step(){ echo; echo "${BOLD}==> $*${RST}"; }
ok(){ echo "  ${GRN}✓${RST} $*"; }
warn(){ echo "  ${YEL}!${RST} $*"; }
die(){ echo "  ${RED}✗ $*${RST}"; exit 1; }

step "Checking this computer"
OS="$(uname -s)"; ARCH="$(uname -m)"
[[ "$OS" == "Darwin" ]] || warn "This installer is designed for macOS (detected $OS). Continuing anyway."
if [[ "$OS" == "Darwin" ]]; then
  ok "macOS $(sw_vers -productVersion) · $(sysctl -n machdep.cpu.brand_string) · $ARCH · $(( $(sysctl -n hw.memsize) / 1073741824 )) GB RAM"
fi

# --- Homebrew (optional but recommended) ---
BREW=""
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [[ -x "$b" ]] && BREW="$b" && break; done
[[ -n "$BREW" ]] && eval "$($BREW shellenv)"

# --- Python 3.10+ ---
step "Python"
PY=""
for c in python3.12 python3.11 python3.13 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    v=$("$c" -c 'import sys;print(sys.version_info[0]*100+sys.version_info[1])')
    if (( v >= 310 )); then PY="$(command -v "$c")"; break; fi
  fi
done
if [[ -z "$PY" ]]; then
  if [[ -n "$BREW" ]]; then
    warn "Python 3.10+ not found — installing python@3.12 with Homebrew"
    "$BREW" install python@3.12
    PY="$("$BREW" --prefix)/bin/python3.12"
  else
    die "Python 3.10+ is required. Install Homebrew (https://brew.sh) then run: brew install python@3.12"
  fi
fi
ok "Using $($PY --version) at $PY"

# --- FFmpeg (system one preferred; bundled fallback via imageio-ffmpeg) ---
step "FFmpeg"
if command -v ffmpeg >/dev/null 2>&1; then ok "ffmpeg found: $(command -v ffmpeg)"
elif [[ -n "$BREW" ]]; then "$BREW" install ffmpeg && ok "ffmpeg installed"
else warn "ffmpeg not found — the bundled imageio-ffmpeg binary will be used"; fi

# --- Virtual environment + packages ---
step "Python packages (first run downloads PyTorch, ~5 min)"
[[ -d .venv ]] || "$PY" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null
python -m pip install -r requirements.txt
ok "Packages installed"
python - <<'PYEOF'
import torch
mps = getattr(torch.backends, "mps", None)
print("  ✓ PyTorch", torch.__version__, "| Apple GPU (MPS):", bool(mps and mps.is_available()))
PYEOF

# --- Folders + database ---
step "Folders & database"
mkdir -p models database recordings/continuous recordings/events snapshots logs config exports
python -c "import sys; sys.path.insert(0,'.'); from backend.app.db import db; print('  ✓ SQLite database ready: database/cctv.db')"
chmod 700 config database

# --- Hardware + camera check, choose model ---
step "Hardware & webcam inspection"
python scripts/system_check.py --write-config || warn "System check reported a problem (see above)"

# --- AI models ---
step "AI models"
python scripts/download_models.py

# --- Frontend (prebuilt dist is included; rebuild only if Node is present and dist missing) ---
step "Dashboard"
if [[ -f frontend/dist/index.html ]]; then
  ok "Prebuilt dashboard found (frontend/dist)"
elif command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install --no-audit --no-fund && npm run build) && ok "Dashboard built"
else
  die "frontend/dist is missing and Node.js is not installed. Run: brew install node, then ./install.sh"
fi

chmod +x start.sh stop.sh scripts/*.sh 2>/dev/null || true
echo
echo "${GRN}${BOLD}Installation complete.${RST}"
echo "  Start:      ./start.sh        (opens http://localhost:8090)"
echo "  Autostart:  ./scripts/install-autostart.sh"
echo "  First visit asks you to create the admin account."
