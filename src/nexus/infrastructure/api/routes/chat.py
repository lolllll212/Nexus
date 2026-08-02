"""
Chat API - the conscious loop's entry point.

This layer is a THIN adapter. It parses HTTP, calls the ProcessMessage
use case, and serializes the result. Zero business logic lives here.

Identity comes from the verified bearer token (dependencies.require_identity);
the body no longer accepts a client-supplied user_id.

Multimodal (P3):
  - `image_urls`: attached to the user turn as vision content blocks.
  - `audio`: a base64 data URI (`data:audio/<mime>;base64,...`) transcribed via
    the SpeechToText adapter and used as (or prefixed to) the message text.
  - `voice`: when set, the response is synthesized to speech via TextToSpeech
    and returned as an audio data URI.
"""

from __future__ import annotations

import base64
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus.infrastructure.api.dependencies import get_container, require_identity, require_rate_limit
from nexus.infrastructure.di.container import Container
from nexus.domain.value_objects.identity import Identity

router = APIRouter(
    prefix="/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_identity), Depends(require_rate_limit("chat"))],
)


class ChatRequest(BaseModel):
    message: str = Field("", min_length=0)
    session_id: Optional[str] = None
    stream: bool = False
    image_urls: Optional[List[str]] = None
    audio: Optional[str] = None       # data URI: data:audio/<mime>;base64,...
    voice: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tools_used: list
    memories_recalled: int
    thought_count: int
    audio: Optional[str] = None       # data URI of synthesized speech (P3)


def _parse_data_uri(data_uri: str) -> tuple[str, bytes]:
    """Split `data:<mime>;base64,<payload>` into (mime, bytes)."""
    head, _, payload = data_uri.partition(",")
    mime = head.removeprefix("data:").split(";")[0] or "audio/mpeg"
    return mime, base64.b64decode(payload, validate=True)


def _to_data_uri(payload: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> ChatResponse:
    message = req.message

    if req.audio:
        try:
            mime, audio_bytes = _parse_data_uri(req.audio)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid audio data URI")
        transcription = await container.speech_to_text.transcribe(audio_bytes, mime)
        message = f"{transcription}\n{message}" if message else transcription

    if not message:
        raise HTTPException(status_code=422, detail="Provide a message, audio, or image")

    result = await container.process_message.execute(
        user_id=identity.user_id,
        message=message,
        session_id=req.session_id,
        stream=req.stream,
        tenant_id=identity.tenant_id,
        image_urls=req.image_urls,
    )

    audio = None
    if req.voice:
        audio_bytes = await container.text_to_speech.synthesize(result.response, req.voice)
        audio = _to_data_uri(audio_bytes, "audio/mpeg")

    return ChatResponse(
        response=result.response,
        session_id=result.session_id,
        tools_used=result.tools_used,
        memories_recalled=result.memories_recalled,
        thought_count=len(result.thoughts),
        audio=audio,
    )
