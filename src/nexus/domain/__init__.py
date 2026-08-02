"""NEXUS - Domain package. The pure core of the brain with zero framework dependencies."""

from nexus.domain.entities.memory import Memory, MemoryType, EmotionalWeight
from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.entities.thought import Thought, ThoughtType
from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.entities.conversation import Conversation, Message, Session

__all__ = [
    "Memory", "MemoryType", "EmotionalWeight",
    "Concept", "SynapticConnection",
    "Thought", "ThoughtType",
    "Tool", "ToolStatus",
    "Conversation", "Message", "Session",
]
