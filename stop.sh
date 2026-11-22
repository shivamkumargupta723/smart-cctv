#!/usr/bin/env bash
# Stop Smart CCTV (works for both foreground and autostart instances)
PLIST="$HOME/Library/LaunchAgents/com.smartcctv.server.plist"
if [[ -f "$PLIST" ]] && launchctl list | grep -q com.smartcctv.server; then
  launchctl unload "$PLIST" && echo "Autostart service stopped (it will start again at next login)."
fi
pkill -f "backend.app.main" && echo "Smart CCTV stopped." || echo "Smart CCTV was not running."
