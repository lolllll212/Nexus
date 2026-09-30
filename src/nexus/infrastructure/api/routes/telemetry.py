"""Prometheus metrics and system telemetry routes for production monitoring."""

import asyncio
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from nexus.infrastructure.api.dependencies import get_container, require_identity
from nexus.infrastructure.api.routes.graph import get_default_second_brain_graph
from nexus.infrastructure.di.container import Container

router = APIRouter(tags=["telemetry"], dependencies=[Depends(require_identity)])

START_TIME = time.time()
REQUEST_COUNTERS: dict[str, int] = {
    "chat": 0,
    "tools": 0,
    "workflows": 0,
    "research": 0,
    "graph": 0,
}


def increment_metric(metric_name: str, count: int = 1) -> None:
    if metric_name in REQUEST_COUNTERS:
        REQUEST_COUNTERS[metric_name] += count
    else:
        REQUEST_COUNTERS[metric_name] = count


async def generate_prometheus_metrics(container: Container) -> str:
    uptime = time.time() - START_TIME
    backend = os.getenv("NEXUS_INFRA_BACKEND", "memory")
    tools = await container.tool_registry.list_all()
    nim_provider = getattr(container, "nim_provider", None)
    has_nim = 1 if (nim_provider and getattr(nim_provider, "has_api_key", False)) else 0
    graph_data = get_default_second_brain_graph()
    nodes_count = len(graph_data.get("nodes", []))
    links_count = len(graph_data.get("links", []))

    lines = [
        "# HELP nexus_uptime_seconds Total seconds since NEXUS cortex started.",
        "# TYPE nexus_uptime_seconds gauge",
        f"nexus_uptime_seconds {uptime:.2f}",
        "",
        "# HELP nexus_active_tools Number of registered tools ready for ReAct execution.",
        "# TYPE nexus_active_tools gauge",
        f"nexus_active_tools {len(tools)}",
        "",
        "# HELP nexus_nim_connected Status of NVIDIA NIM inference provider (1 = active, 0 = simulated).",
        "# TYPE nexus_nim_connected gauge",
        f"nexus_nim_connected {has_nim}",
        "",
        "# HELP nexus_graph_nodes Second Brain knowledge graph active entities.",
        "# TYPE nexus_graph_nodes gauge",
        f"nexus_graph_nodes {nodes_count}",
        "",
        "# HELP nexus_graph_links Second Brain synaptic connections.",
        "# TYPE nexus_graph_links gauge",
        f"nexus_graph_links {links_count}",
        "",
        "# HELP nexus_requests_total Counter of module executions.",
        "# TYPE nexus_requests_total counter",
    ]

    for key, val in REQUEST_COUNTERS.items():
        lines.append(f'nexus_requests_total{{module="{key}"}} {val}')

    lines.append("")
    lines.append(f"# Nexus backend mode: {backend}")
    return "\n".join(lines) + "\n"


@router.get("/api/system/telemetry")
async def system_telemetry(container: Container = Depends(get_container)) -> dict[str, Any]:
    """JSON telemetry endpoint for real-time J.A.R.V.I.S. HUD gauges."""
    uptime = time.time() - START_TIME
    tools = await container.tool_registry.list_all()
    nim_provider = getattr(container, "nim_provider", None)
    graph_data = get_default_second_brain_graph()

    return {
        "status": "online",
        "uptime_seconds": round(uptime, 1),
        "backend_mode": os.getenv("NEXUS_INFRA_BACKEND", "memory"),
        "nim": {
            "configured": nim_provider is not None,
            "has_api_key": getattr(nim_provider, "has_api_key", False) if nim_provider else False,
            "model": (
                getattr(nim_provider, "model", "meta/llama-3.3-70b-instruct") if nim_provider else "None"
            ),
        },
        "tools_count": len(tools),
        "graph_nodes_count": len(graph_data.get("nodes", [])),
        "graph_links_count": len(graph_data.get("links", [])),
        "counters": REQUEST_COUNTERS,
    }


@router.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket) -> None:
    """Stream real-time system and graph telemetry to J.A.R.V.I.S. HUD via WebSocket."""
    await websocket.accept()
    container = getattr(websocket.app.state, "container", None)
    try:
        while True:
            uptime = time.time() - START_TIME
            tools_count = 20
            if container and hasattr(container, "tool_registry"):
                try:
                    tools = await container.tool_registry.list_all()
                    tools_count = len(tools)
                except Exception:
                    pass

            nim_provider = getattr(container, "nim_provider", None) if container else None
            graph_data = get_default_second_brain_graph()

            payload = {
                "type": "telemetry_pulse",
                "uptime_seconds": round(uptime, 1),
                "tools_count": tools_count,
                "graph_nodes_count": len(graph_data.get("nodes", [])),
                "graph_links_count": len(graph_data.get("links", [])),
                "nim_active": getattr(nim_provider, "has_api_key", False) if nim_provider else False,
                "timestamp": time.time(),
            }
            await websocket.send_json(payload)
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
