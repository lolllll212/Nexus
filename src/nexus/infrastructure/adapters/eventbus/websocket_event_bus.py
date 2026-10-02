"""WebSocket event bus - headless fan-out between NEXUS and the outside.

Implements the `EventBus` port: in-process pub/sub behaves like
`InMemoryEventBus`, and every published event is also pushed to connected
WebSocket clients (VS Code extension, agents, dashboards). Clients may
publish events back into the bus, so the orchestrator and the development
environment share one nervous system with no UI text-copying in the loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from nexus.domain.ports.event_bus import Event, EventBus, EventHandler, EventTopic


class WebSocketEventBus(EventBus):
    """In-process pub/sub + WebSocket fan-out/in.

    `serve()` runs the accept loop on a host/port; `stop()` drains handler
    tasks and closes all client sockets. Connection failures never crash the
    bus - a dead client is dropped, the rest keep flowing.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._handler_tasks: set[asyncio.Task] = set()
        self._drain_timeout = 5.0
        self._clients: set[Any] = set()
        self._server: Any = None
        self._serve_task: asyncio.Task | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    async def _dispatch_local(self, event: Event) -> None:
        handlers = self._subscribers.get(event.topic.value, [])
        for handler in handlers:
            task: asyncio.Task = asyncio.ensure_future(handler(event))  # type: ignore[arg-type]
            self._handler_tasks.add(task)
            task.add_done_callback(self._handler_tasks.discard)

    def _broadcast_sync(self, payload: dict[str, Any]) -> None:
        """Send to all clients from a possibly foreign thread.

        Called from `publish` (which may run on any loop); schedules on the
        serving loop when it differs, on the running loop otherwise.
        """
        dead: list[Any] = []
        data = json.dumps(payload, ensure_ascii=False)
        loop = self.loop
        for ws in self._clients:
            try:
                if loop is not None and loop.is_running() and asyncio.get_running_loop() is not loop:
                    asyncio.run_coroutine_threadsafe(ws.send(data), loop)
                else:
                    asyncio.ensure_future(ws.send(data))
            except RuntimeError:
                if loop is not None and loop.is_running():
                    with contextlib.suppress(Exception):
                        asyncio.run_coroutine_threadsafe(ws.send(data), loop)
                else:
                    dead.append(ws)
            except Exception:
                dead.append(ws)
        for ws in dead:
            with contextlib.suppress(Exception):
                self._clients.discard(ws)

    async def publish(self, event: Event) -> None:
        await self._dispatch_local(event)
        if self._clients:
            self._broadcast_sync(
                {
                    "type": "event",
                    "topic": event.topic.value,
                    "payload": event.payload,
                    "id": event.id,
                    "priority": event.priority.value,
                    "correlation_id": event.correlation_id,
                }
            )

    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None:
        self._subscribers.setdefault(topic.value, []).append(handler)

    async def _handle_client(self, ws: Any) -> None:
        self._clients.add(ws)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    await ws.send(json.dumps({"type": "error", "error": "bad json"}))
                    continue
                kind = msg.get("type")
                if kind == "event":
                    try:
                        topic = EventTopic(msg.get("topic", ""))
                    except ValueError:
                        await ws.send(json.dumps({"type": "error", "error": "unknown topic"}))
                        continue
                    event = Event(
                        topic=topic,
                        payload=msg.get("payload", {}),
                        correlation_id=msg.get("correlation_id"),
                    )
                    await self._dispatch_local(event)
                    self._broadcast_sync(
                        {
                            "type": "event",
                            "topic": event.topic.value,
                            "payload": event.payload,
                            "id": event.id,
                        }
                    )
                elif kind == "ping":
                    await ws.send(json.dumps({"type": "pong", "clients": len(self._clients)}))
                else:
                    await ws.send(json.dumps({"type": "error", "error": f"unknown type {kind!r}"}))
        except Exception:
            pass
        finally:
            self._clients.discard(ws)

    async def serve(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """Start the accept loop. Non-blocking: returns after the server is up."""
        import websockets

        self.loop = asyncio.get_running_loop()
        self._server = await websockets.serve(self._handle_client, host, port)

    async def serve_forever(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        await self.serve(host, port)
        if self._server is not None:
            await self._server.serve_forever()

    async def start(self) -> None:
        return None

    async def stop(self, drain_timeout: float | None = None) -> None:
        timeout = self._drain_timeout if drain_timeout is None else drain_timeout
        if self._handler_tasks:
            _, still_pending = await asyncio.wait(self._handler_tasks, timeout=timeout)
            for task in still_pending:
                task.cancel()
            if still_pending:
                await asyncio.gather(*still_pending, return_exceptions=True)
            self._handler_tasks.clear()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        for ws in list(self._clients):
            with contextlib.suppress(Exception):
                await ws.close()
        self._clients.clear()
        self.loop = None

    @property
    def client_count(self) -> int:
        return len(self._clients)
