#!/usr/bin/env bash
# Start Smart CCTV automatically at login (macOS LaunchAgent) and keep it running.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.smartcctv.server.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.smartcctv.server</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$ROOT/start.sh</string><string>--no-browser</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$ROOT/logs/service.out.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/service.err.log</string>
</dict>
</plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "✓ Autostart installed: Smart CCTV starts at login and restarts if it crashes."
echo "  Dashboard: http://localhost:8090"
echo "  If the camera stays offline, allow Camera access for 'python3' in"
echo "  System Settings > Privacy & Security > Camera (see README > Troubleshooting)."
