import asyncio

import pytest

from backend.orchestrator.api_access import DesktopAccessMiddleware


@pytest.mark.parametrize("protocol", ["http", "websocket"])
@pytest.mark.parametrize(
    "client,origin,allowed",
    [
        ("127.0.0.1", "", True),
        ("::1", "tauri://localhost", True),
        ("127.0.0.1", "http://tauri.localhost", True),
        ("127.0.0.1", "http://localhost:1420", True),
        ("127.0.0.1", "https://untrusted.example", False),
        ("127.0.0.1", "http://localhost.attacker.example", False),
        ("127.0.0.1", "null", False),
        ("192.168.1.10", "", False),
        ("192.168.1.10", "tauri://localhost", False),
    ],
)
def test_desktop_access(protocol, client, origin, allowed):
    messages = []
    calls = []

    async def endpoint(scope, receive, send):
        calls.append(scope["path"])

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    scope = {
        "type": protocol,
        "path": "/api/settings",
        "client": (client, 12345),
        "headers": [(b"origin", origin.encode())] if origin else [],
    }
    asyncio.run(DesktopAccessMiddleware(endpoint)(scope, receive, send))
    assert bool(calls) == allowed
    if not allowed:
        if protocol == "http":
            assert messages[0]["status"] == 403
        else:
            assert messages[0] == {"type": "websocket.close", "code": 1008}


def test_public_api_keeps_its_own_authentication():
    calls = []

    async def endpoint(scope, receive, send):
        calls.append(scope["path"])

    scope = {"type": "http", "path": "/v1/audio/speech", "client": ("192.168.1.10", 12345)}
    asyncio.run(DesktopAccessMiddleware(endpoint)(scope, None, None))
    assert calls == ["/v1/audio/speech"]
