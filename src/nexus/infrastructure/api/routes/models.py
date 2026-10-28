"""
Model Catalog API — the model changer's source of truth.

Serves the Claude-style model picker in the web chat: every NVIDIA NIM model
the operator can switch to, enriched with the capability metadata the
capabilities panel renders (extended thinking / tool use / vision / code /
long context / research / streaming), plus which model is active by default
and whether a live NVIDIA key is configured (live vs simulation).

Selecting a model is a per-request affair: the chat endpoints accept a
`model` field and run that single request on the chosen NIM model without
mutating the shared provider, so this catalog never needs a write endpoint.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from nexus.domain.value_objects.coding_excellence import coding_capability_catalog
from nexus.infrastructure.adapters.llm.nvidia_nim_provider import SUPPORTED_NIM_MODELS
from nexus.infrastructure.api.dependencies import get_container, require_identity
from nexus.infrastructure.di.container import Container

router = APIRouter(
    prefix="/api/models",
    tags=["models"],
    dependencies=[Depends(require_identity)],
)

# Human labels for the capability keys carried by SUPPORTED_NIM_MODELS and
# rendered by the capabilities panel.
CAPABILITY_LABELS = {
    "reasoning": "Extended thinking",
    "tool_use": "Tool use",
    "code": "Code & artifacts",
    "vision": "Vision (images)",
    "long_context": "Long context",
    "research": "Deep research",
    "streaming": "Streaming replies",
}

AUTO_MODEL = {
    "id": "auto",
    "name": "NEXUS Auto",
    "provider": "NEXUS Cortex",
    "description": "Adaptive execution on the configured cortex: Nexus profiles task complexity and coding focus, then on NVIDIA NIM routes simple work to a fast model, hard work to a deep/flagship model, coding to a code-capable model, and images to a vision model—before quality-checking the result.",
    "tags": ["auto", "cortex", "adaptive"],
    "context_window": None,
    "speed": "balanced",
    "best_for": "Best default: effort- and coding-aware routing for clean UI, C, C++, Rust, Python, PHP, HTML5, XML, and Ruby with tools, verification, and repair",
    "capabilities": ["reasoning", "tool_use", "code", "vision", "long_context", "research", "streaming"],
}


@router.get("")
async def list_models(container: Container = Depends(get_container)) -> dict[str, Any]:
    """List selectable chat models with capabilities + provider status."""
    provider = getattr(container, "nim_provider", None)
    active_model = getattr(provider, "model", None) if provider is not None else None
    has_key = bool(getattr(provider, "has_api_key", False)) if provider is not None else False
    execution_config = getattr(container, "ai_execution_config", None)
    execution_config = dict(execution_config) if isinstance(execution_config, dict) else {}
    adaptive_routing = bool(
        provider is not None and getattr(container, "llm", None) is provider
    )

    models: list[dict[str, Any]] = [dict(AUTO_MODEL, is_active=False, source="nexus-default")]
    default_model = active_model
    for entry in SUPPORTED_NIM_MODELS:
        model: dict[str, Any] = dict(entry)
        model.setdefault("capabilities", ["tool_use", "streaming"])
        model.setdefault("context_window", None)
        model.setdefault("speed", "balanced")
        model.setdefault("best_for", "")
        model["source"] = "nvidia-nim"
        model["is_active"] = model["id"] == active_model
        if "default" in (model.get("tags") or []) and default_model is None:
            default_model = model["id"]
        models.append(model)

    return {
        "models": models,
        "active_model": active_model,
        "default_model": default_model or "auto",
        "provider_status": "live" if has_key else "simulation",
        "has_api_key": has_key,
        "capability_labels": CAPABILITY_LABELS,
        "coding": coding_capability_catalog(),
        "execution": {
            "efforts": ["auto", "fast", "balanced", "deep", "max"],
            "default_effort": execution_config.get("default_effort", "auto"),
            "adaptive_model_routing": adaptive_routing,
            "quality_gate_enabled": bool(
                execution_config.get("quality_gate_enabled", True)
            ),
            "native_tool_calling_enabled": bool(
                execution_config.get("native_tool_calling_enabled", True)
            ),
            "quality_max_repairs": int(execution_config.get("quality_max_repairs", 3)),
        },
    }
