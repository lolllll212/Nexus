"""
Event bus ports - the nervous system connecting cortex and subcortex.

Publish/subscribe decouples the two loops. The conscious engine emits events
without knowing or caring who consumes them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional
from uuid import uuid4


class EventTopic(Enum):
    """Canonical event topics on the bus."""
    USER_MESSAGE = "cortex.user_message"
    CONTEXT_INJECTION = "subcortex.context_injection"
    MEMORY_STORED = "memory.stored"
    CONCEPT_ACCESSED = "memory.concept_accessed"
    TOOL_REGISTERED = "tools.registered"
    TOOL_GENERATION_REQUESTED = "tools.generation_requested"
    TOOL_GENERATED = "tools.generated"
    TOOL_GENERATION_FAILED = "tools.generation_failed"
    DREAM_TRIGGERED = "dreaming.triggered"
    DREAM_COMPLETED = "dreaming.completed"
    DREAM_FAILED = "dreaming.failed"
    KNOWLEDGE_UPDATED = "knowledge.updated"
    SYSTEM_HEALTH = "system.health"


class EventPriority(Enum):
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class Event:
    """An event flowing through the nervous system."""

    topic: EventTopic
    payload: Dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4()))
    priority: EventPriority = EventPriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None


EventHandler = Callable[[Event], Awaitable[None]]


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: Event) -> None: ...


class EventSubscriber(ABC):
    @abstractmethod
    async def subscribe(self, topic: EventTopic, handler: EventHandler) -> None: ...


class EventBus(EventPublisher, EventSubscriber):
    """Full bus: publish and subscribe."""
    ...
