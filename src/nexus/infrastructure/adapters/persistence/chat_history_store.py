"""Chat history store — persistent conversation sessions for the history window.

A lightweight, local-first store backing the Claude-style " past conversations"
UX in the web chat: named sessions the operator can reopen, rename, search
and delete, synced server-side so history follows the user across devices.

Design notes:
- One JSON document on disk (``data/chat_history.json`` by default, path from
  ``NEXUS_HISTORY_PATH`` via container config). Writes are atomic
  (tmp file + ``os.replace``) so a crash mid-write never corrupts history.
- ``path=None`` gives a pure in-memory store (tests, ephemeral deploys).
- Every session is owned by ``(tenant_id, user_id)``; all lookups are scoped
  by owner so one identity can never read another's conversations.
- Bounded growth: per-owner session cap and per-session message cap with
  oldest-first pruning keep the file small forever.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("nexus.chat_history")

MAX_SESSIONS_PER_OWNER = 200
MAX_MESSAGES_PER_SESSION = 500
TITLE_MAX_CHARS = 80

_VALID_ROLES = {"user", "assistant", "system", "nexus"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive_title(messages: list[dict[str, Any]]) -> str:
    """Claude-style auto title: first user message, trimmed to a label."""
    for msg in messages:
        if msg.get("role") == "user" and str(msg.get("content") or "").strip():
            text = " ".join(str(msg["content"]).split())
            return text[:TITLE_MAX_CHARS].rstrip() + ("…" if len(text) > TITLE_MAX_CHARS else "")
    return "New conversation"


def _normalize_message(raw: dict[str, Any]) -> dict[str, Any]:
    role = str(raw.get("role") or "user").lower()
    if role not in _VALID_ROLES:
        role = "user"
    # The cortex emits "nexus" for assistant turns; the UI speaks "assistant".
    if role == "nexus":
        role = "assistant"
    msg: dict[str, Any] = {
        "id": str(raw.get("id") or uuid.uuid4()),
        "role": role,
        "content": str(raw.get("content") or ""),
        "timestamp": str(raw.get("timestamp") or _now_iso()),
    }
    if raw.get("model"):
        msg["model"] = str(raw["model"])
    if raw.get("tools_used"):
        msg["tools_used"] = [str(t) for t in raw["tools_used"]]
    return msg


class ChatHistoryStore:
    """Thread-safe session store with optional JSON-file persistence."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._loaded = False

    # ── persistence internals ──────────────────────────────────────────── #

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self._path is None or not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            sessions = data.get("sessions") if isinstance(data, dict) else None
            if isinstance(sessions, dict):
                self._sessions = {str(k): v for k, v in sessions.items() if isinstance(v, dict)}
        except Exception as exc:  # a corrupt history file must never break chat
            logger.warning("chat history file unreadable (%s); starting empty", exc)
            self._sessions = {}

    def _flush_locked(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(
                json.dumps({"sessions": self._sessions}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.warning("failed to persist chat history: %s", exc)

    # ── helpers ────────────────────────────────────────────────────────── #

    @staticmethod
    def _owned(session: dict[str, Any], user_id: str, tenant_id: str) -> bool:
        return session.get("user_id") == user_id and session.get("tenant_id") == tenant_id

    @staticmethod
    def _summary(session: dict[str, Any]) -> dict[str, Any]:
        messages = session.get("messages") or []
        preview = ""
        for msg in reversed(messages):
            if str(msg.get("content") or "").strip():
                preview = " ".join(str(msg["content"]).split())[:140]
                break
        return {
            "id": session["id"],
            "title": session.get("title") or "New conversation",
            "model": session.get("model"),
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "message_count": len(messages),
            "preview": preview,
        }

    def _prune_owner_locked(self, user_id: str, tenant_id: str) -> None:
        owned = [s for s in self._sessions.values() if self._owned(s, user_id, tenant_id)]
        if len(owned) <= MAX_SESSIONS_PER_OWNER:
            return
        owned.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        for stale in owned[MAX_SESSIONS_PER_OWNER:]:
            self._sessions.pop(stale["id"], None)

    def _get_owned_locked(self, session_id: str, user_id: str, tenant_id: str) -> dict[str, Any] | None:
        session = self._sessions.get(session_id)
        if session is None or not self._owned(session, user_id, tenant_id):
            return None
        return session

    # ── public API ─────────────────────────────────────────────────────── #

    def create_session(
        self,
        user_id: str,
        tenant_id: str = "default",
        title: str | None = None,
        model: str | None = None,
        session_id: str | None = None,
        messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            if session_id and (existing := self._get_owned_locked(session_id, user_id, tenant_id)):
                return dict(existing)
            requested_id = session_id
            if requested_id and requested_id in self._sessions:
                # The ID belongs to another owner. Never overwrite their
                # conversation; issue this caller a fresh session ID instead.
                requested_id = str(uuid.uuid4())
            normalized = [_normalize_message(m) for m in (messages or [])]
            now = _now_iso()
            session = {
                "id": requested_id or str(uuid.uuid4()),
                "user_id": user_id,
                "tenant_id": tenant_id,
                "title": (title or _derive_title(normalized))[:TITLE_MAX_CHARS],
                "model": model,
                "created_at": now,
                "updated_at": now,
                "messages": normalized[-MAX_MESSAGES_PER_SESSION:],
            }
            self._sessions[session["id"]] = session
            self._prune_owner_locked(user_id, tenant_id)
            self._flush_locked()
            return dict(session)

    def list_sessions(
        self,
        user_id: str,
        tenant_id: str = "default",
        query: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._lock:
            self._ensure_loaded()
            owned = [s for s in self._sessions.values() if self._owned(s, user_id, tenant_id)]
            if query:
                needle = query.lower()
                owned = [
                    s
                    for s in owned
                    if needle in str(s.get("title") or "").lower()
                    or any(needle in str(m.get("content") or "").lower() for m in s.get("messages") or [])
                ]
            owned.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
            return [self._summary(s) for s in owned[: max(1, min(limit, 200))]]

    def get_session(
        self, session_id: str, user_id: str, tenant_id: str = "default"
    ) -> dict[str, Any] | None:
        with self._lock:
            self._ensure_loaded()
            session = self._get_owned_locked(session_id, user_id, tenant_id)
            return dict(session) if session else None

    def append_messages(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str = "default",
        messages: list[dict[str, Any]] | None = None,
        model: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any] | None:
        """Append turns; auto-creates the session if this is its first turn."""
        with self._lock:
            self._ensure_loaded()
            session = self._get_owned_locked(session_id, user_id, tenant_id)
            normalized = [_normalize_message(m) for m in (messages or [])]
            if session is None:
                if session_id in self._sessions:
                    return None  # exists but owned by someone else
                now = _now_iso()
                session = {
                    "id": session_id,
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "title": (title or _derive_title(normalized))[:TITLE_MAX_CHARS],
                    "model": model,
                    "created_at": now,
                    "updated_at": now,
                    "messages": [],
                }
                self._sessions[session_id] = session
                self._prune_owner_locked(user_id, tenant_id)

            seen = {m["id"] for m in session["messages"]}
            for msg in normalized:
                if msg["id"] not in seen:  # idempotent re-sync from the UI
                    session["messages"].append(msg)
                    seen.add(msg["id"])
            session["messages"] = session["messages"][-MAX_MESSAGES_PER_SESSION:]
            if model:
                session["model"] = model
            if title:
                session["title"] = title[:TITLE_MAX_CHARS]
            elif session.get("title") in (None, "", "New conversation"):
                session["title"] = _derive_title(session["messages"])[:TITLE_MAX_CHARS]
            session["updated_at"] = _now_iso()
            self._flush_locked()
            return dict(session)

    def rename_session(
        self, session_id: str, title: str, user_id: str, tenant_id: str = "default"
    ) -> dict[str, Any] | None:
        with self._lock:
            self._ensure_loaded()
            session = self._get_owned_locked(session_id, user_id, tenant_id)
            if session is None:
                return None
            session["title"] = title.strip()[:TITLE_MAX_CHARS] or session["title"]
            session["updated_at"] = _now_iso()
            self._flush_locked()
            return dict(session)

    def delete_session(self, session_id: str, user_id: str, tenant_id: str = "default") -> bool:
        with self._lock:
            self._ensure_loaded()
            if self._get_owned_locked(session_id, user_id, tenant_id) is None:
                return False
            self._sessions.pop(session_id, None)
            self._flush_locked()
            return True

    def clear(self, user_id: str, tenant_id: str = "default") -> int:
        """Delete every session of one owner. Returns how many were removed."""
        with self._lock:
            self._ensure_loaded()
            doomed = [sid for sid, s in self._sessions.items() if self._owned(s, user_id, tenant_id)]
            for sid in doomed:
                self._sessions.pop(sid, None)
            if doomed:
                self._flush_locked()
            return len(doomed)
