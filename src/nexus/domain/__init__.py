"""NEXUS - Domain package. The pure core of the brain with zero framework dependencies."""

from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.entities.conversation import Conversation, Message, Session
from nexus.domain.entities.memory import EmotionalWeight, Memory, MemoryType
from nexus.domain.entities.thought import Thought, ThoughtType
from nexus.domain.entities.tool import Tool, ToolStatus

__all__ = [
    "Concept",
    "Conversation",
    "EmotionalWeight",
    "Memory",
    "MemoryType",
    "Message",
    "Session",
    "SynapticConnection",
    "Thought",
    "ThoughtType",
    "Tool",
    "ToolStatus",
]
