#!/usr/bin/env bash
# Start Smart CCTV and open the dashboard. Use --no-browser for background/autostart.
set -euo pipefail
cd "$(dirname "$0")"
[[ -d .venv ]] || { echo "Not installed yet — run ./install.sh first"; exit 1; }
for b in /opt/homebrew/bin /usr/local/bin; do [[ -d "$b" ]] && export PATH="$b:$PATH"; done
source .venv/bin/activate
PORT="${CCTV_PORT:-8090}"
if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Smart CCTV already running on http://localhost:$PORT"
  [[ "${1:-}" == "--no-browser" ]] || open "http://localhost:$PORT" 2>/dev/null || true
  exit 0
fi
if [[ "${1:-}" != "--no-browser" ]]; then
  ( for i in $(seq 1 60); do
      sleep 1
      if curl -s -o /dev/null "http://127.0.0.1:$PORT/api/auth/state"; then open "http://localhost:$PORT" 2>/dev/null || true; break; fi
    done ) &
fi
echo "Starting Smart CCTV on http://localhost:$PORT  (Ctrl+C to stop)"
exec python -m backend.app.main
