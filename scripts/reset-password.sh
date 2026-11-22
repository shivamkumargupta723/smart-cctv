#!/usr/bin/env bash
# Reset the dashboard admin password (run on this Mac only).
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
read -rp "Username [admin]: " U; U=${U:-admin}
read -rsp "New password (8+ chars): " P; echo
python - "$U" "$P" <<'PY'
import sys, time
sys.path.insert(0, ".")
from backend.app.db import db
from backend.app.auth import hash_password
u, p = sys.argv[1], sys.argv[2]
assert len(p) >= 8, "Password must be at least 8 characters"
if db.one("SELECT id FROM users WHERE username=?", (u,)):
    db.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(p), u))
else:
    db.insert("users", {"username": u, "password_hash": hash_password(p), "created_at": time.time()})
db.execute("DELETE FROM sessions")
print("✓ Password updated; all sessions signed out.")
PY
