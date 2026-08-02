"""
Chat API - the conscious loop's entry point.

This layer is a THIN adapter. It parses HTTP, calls the ProcessMessage
use case, and serializes the result. Zero business logic lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Optional

from nexus.infrastructure.api.dependencies import get_container
from nexus.infrastructure.di.container import Container

router = APIRouter(prefix="/v1/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: str = "anonymous"
    session_id: Optional[str] = None
    stream: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tools_used: list
    memories_recalled: int
    thought_count: int


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, container: Container = Depends(get_container)) -> ChatResponse:
    result = await container.process_message.execute(
        user_id=req.user_id,
        message=req.message,
        session_id=req.session_id,
        stream=req.stream,
    )

    return ChatResponse(
        response=result.response,
        session_id=result.session_id,
        tools_used=result.tools_used,
        memories_recalled=result.memories_recalled,
        thought_count=len(result.thoughts),
    )
