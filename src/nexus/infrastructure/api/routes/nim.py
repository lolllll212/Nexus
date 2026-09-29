"""
NVIDIA NIM (NVIDIA Inference Microservice) API routes.

Provides endpoints to interact with NVIDIA NIM LLM models, test status,
list available NIM models, configure API keys and active models,
and query the J.A.R.V.I.S. reasoning cortex powered by NVIDIA NIM.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from nexus.infrastructure.adapters.llm.nvidia_nim_provider import (
    SUPPORTED_NIM_MODELS,
    NvidiaNimProvider,
)
from nexus.infrastructure.api.dependencies import get_container, require_admin, require_identity
from nexus.infrastructure.di.container import Container

logger = logging.getLogger("nexus.nim.api")

router = APIRouter(prefix="/api/nim", tags=["nvidia-nim"], dependencies=[Depends(require_identity)])


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class NimChatRequest(BaseModel):
    prompt: str | None = None
    messages: list[ChatMessage] | None = None
    model: str | None = None
    tier: str | None = "cortex"
    system_prompt: str | None = (
        "You are J.A.R.V.I.S., an advanced AI operating system assistant and Second Brain "
        "knowledge navigator. Respond concisely, intelligently, and with polite Stark-like technical precision."
    )
    temperature: float = Field(0.5, ge=0.0, le=2.0)
    max_tokens: int | None = Field(1024, ge=1, le=8192)


class NimChatResponse(BaseModel):
    response: str
    model: str
    provider: str = "nvidia_nim"
    status: str = "ok"
    has_real_key: bool = False


class NimConfigRequest(BaseModel):
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None


class NimStatusResponse(BaseModel):
    enabled: bool
    has_api_key: bool
    masked_key: str
    base_url: str
    active_model: str
    status: str
    supported_models: list[dict[str, Any]]


def _get_nim_provider(container: Container) -> NvidiaNimProvider:
    provider = getattr(container, "nim_provider", None)
    if provider is None:
        # Fallback creation if not wired
        provider = NvidiaNimProvider()
        container.nim_provider = provider
    return provider


@router.get("/status", response_model=NimStatusResponse)
async def get_nim_status(container: Container = Depends(get_container)) -> NimStatusResponse:
    """Return current status of NVIDIA NIM integration."""
    provider = _get_nim_provider(container)
    key = getattr(provider, "_api_key", "")
    has_key = provider.has_api_key

    if has_key:
        masked = f"{key[:7]}...{key[-4:]}" if len(key) > 11 else "nvapi-configured"
        status = "ready"
    else:
        masked = "None (simulation active)"
        status = "simulation"

    return NimStatusResponse(
        enabled=True,
        has_api_key=has_key,
        masked_key=masked,
        base_url=provider.base_url,
        active_model=provider.model,
        status=status,
        supported_models=SUPPORTED_NIM_MODELS,
    )


@router.get("/models")
async def list_nim_models(container: Container = Depends(get_container)) -> dict[str, Any]:
    """List all supported NVIDIA NIM models and descriptions."""
    provider = _get_nim_provider(container)
    return {
        "active_model": provider.model,
        "models": SUPPORTED_NIM_MODELS,
    }


@router.post("/chat", response_model=NimChatResponse)
async def chat_nim(
    req: NimChatRequest,
    container: Container = Depends(get_container),
) -> NimChatResponse:
    """Send a prompt or conversation history to NVIDIA NIM."""
    provider = _get_nim_provider(container)

    # Allow temporary model override per-request
    original_model = provider.model
    if req.model:
        provider.model = req.model

    try:
        messages: list[dict[str, str]] = []
        if req.system_prompt:
            messages.append({"role": "system", "content": req.system_prompt})

        if req.messages:
            for m in req.messages:
                messages.append({"role": m.role, "content": m.content})
        elif req.prompt:
            messages.append({"role": "user", "content": req.prompt})
        else:
            raise HTTPException(status_code=400, detail="Either 'prompt' or 'messages' must be provided.")

        reply = await provider.complete(
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

        return NimChatResponse(
            response=reply,
            model=provider.model,
            provider="nvidia_nim",
            status="ok",
            has_real_key=provider.has_api_key,
        )
    finally:
        if req.model and original_model != req.model:
            provider.model = original_model


@router.post("/chat/stream")
async def chat_nim_stream(
    req: NimChatRequest,
    container: Container = Depends(get_container),
):
    """Stream token-by-token response from NVIDIA NIM via Server-Sent Events (SSE)."""
    provider = _get_nim_provider(container)
    tier_model = getattr(provider, "get_tier_model", lambda t: provider.model)(req.tier or "cortex")
    model_name = req.model or tier_model

    messages: list[dict[str, str]] = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})

    if req.messages:
        for m in req.messages:
            messages.append({"role": m.role, "content": m.content})
    elif req.prompt:
        messages.append({"role": "user", "content": req.prompt})

    async def token_generator():
        try:
            meta = json.dumps({"type": "start", "model": model_name, "provider": "nvidia_nim"})
            yield f"data: {meta}\n\n"

            async for token in provider.stream(
                messages,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
            ):
                payload = json.dumps({"type": "token", "content": token})
                yield f"data: {payload}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            err = json.dumps({"type": "error", "error": str(e)})
            yield f"data: {err}\n\n"

    return StreamingResponse(token_generator(), media_type="text/event-stream")


@router.post("/configure")
async def configure_nim(
    req: NimConfigRequest,
    container: Container = Depends(get_container),
    admin: Any = Depends(require_admin),
) -> dict[str, Any]:
    """Dynamically update NVIDIA NIM credentials or model configuration (Admin only)."""
    provider = _get_nim_provider(container)

    if req.api_key is not None:
        provider.set_api_key(req.api_key)
        # Also update container config if present
        if hasattr(container, "config") and container.config is not None:
            container.config.nvidia_api_key = req.api_key

    if req.model:
        provider.model = req.model
        if hasattr(container, "config") and container.config is not None:
            container.config.nim_model = req.model

    if req.base_url:
        provider.base_url = req.base_url
        if hasattr(container, "config") and container.config is not None:
            container.config.nim_base_url = req.base_url

    return {
        "status": "updated",
        "has_api_key": provider.has_api_key,
        "active_model": provider.model,
        "base_url": provider.base_url,
    }


@router.get("/verify")
async def verify_nim_connection(
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Verify live connectivity with NVIDIA NIM endpoint."""
    provider = _get_nim_provider(container)
    return await provider.verify_connection()
