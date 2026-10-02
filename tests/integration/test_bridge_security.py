from __future__ import annotations

import json

from nexus.infrastructure.adapters.eventbus.websocket_event_bus import WebSocketEventBus
from scripts.ide_bridge import handle_cmd


class FakeWS:
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])
        self.sent: list[dict] = []
        self.closed = False

    async def recv(self) -> str:
        if not self._responses:
            raise RuntimeError("no more ws responses")
        return self._responses.pop(0)

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def close(self) -> None:
        self.closed = True


async def test_auth_rejects_invalid_token(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_BRIDGE_TOKEN", "super-secret")
    bus = WebSocketEventBus()
    ws = FakeWS(['{"type": "auth", "token": "wrong"}'])

    allowed = await bus._authenticate(ws, None)

    assert allowed is False
    assert ws.sent[-1]["type"] == "error"
    assert ws.sent[-1]["error"] == "auth required"


async def test_bridge_default_allowlist_denies_run_and_edit(monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_BRIDGE_TOKEN", raising=False)
    monkeypatch.setenv("NEXUS_BRIDGE_ALLOWLIST", "ping,open")
    monkeypatch.setenv("NEXUS_BRIDGE_RATE_LIMIT", "2")
    monkeypatch.setenv("NEXUS_BRIDGE_RATE_WINDOW_SECONDS", "60")

    bus = WebSocketEventBus()
    assert bus._is_allowed("ping") is True
    assert bus._is_allowed("open") is True
    assert bus._is_allowed("run") is False
    assert bus._is_allowed("edit") is False
    assert bus._check_rate_limit("ping") is True
    assert bus._check_rate_limit("ping") is True
    assert bus._check_rate_limit("ping") is False


def test_ide_bridge_enforces_rate_limits_and_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_BRIDGE_ALLOWLIST", "ping,open")
    monkeypatch.setenv("NEXUS_BRIDGE_RATE_LIMIT", "1")
    monkeypatch.setenv("NEXUS_BRIDGE_RATE_WINDOW_SECONDS", "60")

    first = handle_cmd("run", {"args": ["python", "-c", "print(1)"]})
    second = handle_cmd("run", {"args": ["python", "-c", "print(1)"]})
    blocked = handle_cmd("edit", {"path": "README.md", "content": "x"})

    assert first["ok"] is False
    assert "not allowed" in first["error"]
    assert second["ok"] is False
    assert "not allowed" in second["error"]
    assert blocked["ok"] is False
    assert "not allowed" in blocked["error"]
