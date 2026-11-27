"""Keep desktop control endpoints private when the public API binds to LAN."""

import re

from starlette.responses import JSONResponse


DESKTOP_ORIGINS = ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"]
DEV_ORIGIN_PATTERN = r"https?://(localhost|127\.0\.0\.1)(:[0-9]+)?"


class DesktopAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"} or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("latin-1")
        local = bool(client and client[0] in {"127.0.0.1", "::1"})
        trusted_origin = not origin or origin in DESKTOP_ORIGINS or re.fullmatch(DEV_ORIGIN_PATTERN, origin)
        if local and trusted_origin:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            response = JSONResponse({"detail": "Desktop endpoints require a local, trusted client."}, status_code=403)
            await response(scope, receive, send)
