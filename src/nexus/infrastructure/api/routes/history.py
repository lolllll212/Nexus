"""
Chat History API — server-side conversation sessions for the history window.

Backs the Claude-style "past conversations" drawer in the web chat:
list / create / open / rename / delete named sessions, each holding the
full user+assistant transcript. Storage lives in
`ChatHistoryStore` (file-backed JSON, see adapters/persistence); this layer
is a thin adapter that scopes every operation to the verified identity.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from nexus.domain.value_objects.identity import Identity
from nexus.infrastructure.api.dependencies import get_container, require_identity
from nexus.infrastructure.di.container import Container

router = APIRouter(
    prefix="/api/history",
    tags=["chat-history"],
    dependencies=[Depends(require_identity)],
)


class HistoryMessageIn(BaseModel):
    id: str | None = None
    role: str = "user"  # user | assistant | system
    content: str = ""
    timestamp: str | None = None
    model: str | None = None
    tools_used: list[str] | None = None


class CreateSessionRequest(BaseModel):
    title: str | None = None
    model: str | None = None
    session_id: str | None = None
    messages: list[HistoryMessageIn] | None = None


class AppendMessagesRequest(BaseModel):
    messages: list[HistoryMessageIn] = Field(default_factory=list)
    model: str | None = None
    title: str | None = None


class RenameSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


def _get_store(container: Container):
    store = getattr(container, "history_store", None)
    if store is None:
        # Fallback for containers built before history wiring (e.g. test
        # fakes): a process-local in-memory store attached to the container.
        from nexus.infrastructure.adapters.persistence.chat_history_store import ChatHistoryStore

        store = ChatHistoryStore(path=None)
        container.history_store = store
    return store


def _messages(payload: list[HistoryMessageIn] | None) -> list[dict[str, Any]]:
    return [m.model_dump(exclude_none=True) for m in (payload or [])]


@router.get("/sessions")
async def list_sessions(
    q: str | None = None,
    limit: int = 50,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """List the caller's conversation sessions, newest activity first."""
    store = _get_store(container)
    sessions = store.list_sessions(identity.user_id, identity.tenant_id, query=q, limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@router.post("/sessions", status_code=201)
async def create_session(
    req: CreateSessionRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    store = _get_store(container)
    session = store.create_session(
        user_id=identity.user_id,
        tenant_id=identity.tenant_id,
        title=req.title,
        model=req.model,
        session_id=req.session_id,
        messages=_messages(req.messages),
    )
    return {"session": session}


@router.delete("/sessions")
async def clear_sessions(
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Delete every session belonging to the caller."""
    store = _get_store(container)
    deleted = store.clear(identity.user_id, identity.tenant_id)
    return {"deleted": deleted}


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    store = _get_store(container)
    session = store.get_session(session_id, identity.user_id, identity.tenant_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"session": session}


@router.post("/sessions/{session_id}/messages")
async def append_messages(
    session_id: str,
    req: AppendMessagesRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    """Append turns to a session (auto-created on its first turn).

    Message ids make this idempotent, so the UI can safely re-sync a whole
    transcript without duplicating turns.
    """
    store = _get_store(container)
    session = store.append_messages(
        session_id,
        identity.user_id,
        identity.tenant_id,
        messages=_messages(req.messages),
        model=req.model,
        title=req.title,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"session": session}


@router.patch("/sessions/{session_id}")
async def rename_session(
    session_id: str,
    req: RenameSessionRequest,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    store = _get_store(container)
    session = store.rename_session(session_id, req.title, identity.user_id, identity.tenant_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"session": session}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    identity: Identity = Depends(require_identity),
    container: Container = Depends(get_container),
) -> dict[str, Any]:
    store = _get_store(container)
    if not store.delete_session(session_id, identity.user_id, identity.tenant_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"deleted": True, "id": session_id}
