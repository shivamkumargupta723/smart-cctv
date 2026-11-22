"""WebSocket hub: thread-safe broadcast from worker threads to browsers."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

log = logging.getLogger("hub")


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop):
        self.loop = loop

    async def add(self, ws: WebSocket):
        self.clients.add(ws)

    def remove(self, ws: WebSocket):
        self.clients.discard(ws)

    async def _send_all(self, text: str):
        dead = []
        for ws in list(self.clients):
            try:
                await asyncio.wait_for(ws.send_text(text), timeout=2)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def broadcast(self, msg_type: str, data):
        """Callable from any thread."""
        if not self.loop or not self.clients:
            return
        text = json.dumps({"type": msg_type, "data": data}, default=str)
        try:
            asyncio.run_coroutine_threadsafe(self._send_all(text), self.loop)
        except RuntimeError:
            pass


hub = Hub()
