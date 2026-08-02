"""Domain conversation entities - the working memory of the conscious loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

from nexus.domain.value_objects.emotion import EmotionalState, infer_emotional_state


class MessageRole(Enum):
    USER = "user"
    NEXUS = "nexus"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    """A single message within a conversation."""

    role: MessageRole
    content: str
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class Session:
    """A persistent interaction session."""

    session_id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = "anonymous"
    tenant_id: str = "default"
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class Conversation:
    """The short-term working context of the conscious loop."""

    session_id: str
    user_id: str
    tenant_id: str = "default"
    messages: List[Message] = field(default_factory=list)
    active_concepts: List[str] = field(default_factory=list)
    emotional_state: EmotionalState = field(default_factory=EmotionalState)
    current_task: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_message(self, role: MessageRole, content: str, metadata: Dict = None) -> Message:
        msg = Message(role=role, content=content, metadata=metadata or {})
        self.messages.append(msg)
        self.updated_at = datetime.utcnow()
        return msg

    def observe_message(self, role: MessageRole, content: str) -> None:
        """Update the room's emotional state from an incoming message (the seed for tone)."""
        if role == MessageRole.USER:
            self.emotional_state = self.emotional_state.blend(infer_emotional_state(content))

    def recent(self, n: int = 10) -> List[Message]:
        return self.messages[-n:]

    def to_llm_context(self, n: int = 10) -> List[Dict[str, str]]:
        """Serialize recent messages for LLM consumption."""
        return [
            {"role": m.role.value, "content": m.content}
            for m in self.recent(n)
        ]
