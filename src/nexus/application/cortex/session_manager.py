"""
SessionManager - manages the working memory of the conscious loop.

Pure application logic backed by the ShortTermMemory port.
"""

from __future__ import annotations

from typing import Optional

from nexus.domain.entities.conversation import Conversation, Session
from nexus.domain.ports.memory_repository import ShortTermMemory


class SessionManager:
    """Creates and restores conversation sessions."""

    def __init__(self, working_memory: ShortTermMemory) -> None:
        self._working_memory = working_memory
        self._cache: dict[str, Conversation] = {}

    async def get_or_create(self, session_id: Optional[str], user_id: str) -> Conversation:
        if session_id and session_id in self._cache:
            return self._cache[session_id]

        if session_id:
            restored = await self._working_memory.get(f"session:{session_id}")
            if restored:
                conv = Conversation(
                    session_id=session_id,
                    user_id=user_id,
                )
                # Rebuild recent messages from restored context
                for msg in restored.get("recent", []):
                    from nexus.domain.entities.conversation import MessageRole

                    conv.messages.append(
                        Conversation(session_id, user_id).add_message(MessageRole(msg["role"]), msg["content"])
                    )
                self._cache[session_id] = conv
                return conv

        conv = Conversation(session_id=session_id or str(__import__("uuid").uuid4()), user_id=user_id)
        self._cache[conv.session_id] = conv
        return conv
