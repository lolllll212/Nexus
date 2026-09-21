"""
NEXUS Ports - the interfaces that decouple domain/application from infrastructure.

These are the "ports" of Hexagonal (Ports & Adapters) architecture.
The application depends ONLY on these abstractions, never on concrete
implementations. Swapping Redis for Kafka, OpenAI for Llama, or Neo4j for
a different graph DB requires writing a new adapter - zero changes to the brain.
"""

from nexus.domain.ports.memory_repository import MemoryRepository, ConceptRepository, ShortTermMemory
from nexus.domain.ports.llm_provider import LLMProvider, StreamingLLMProvider, EmbeddingProvider
from nexus.domain.ports.event_bus import EventBus, Event, EventSubscriber, EventPublisher
from nexus.domain.ports.tool_registry import ToolRegistry
from nexus.domain.ports.deployment import DeploymentProvider
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.sandbox import Sandbox

__all__ = [
    "MemoryRepository",
    "ConceptRepository",
    "ShortTermMemory",
    "LLMProvider",
    "StreamingLLMProvider",
    "EmbeddingProvider",
    "EventBus",
    "Event",
    "EventSubscriber",
    "EventPublisher",
    "ToolRegistry",
    "DeploymentProvider",
    "ToolExecutor",
    "Sandbox",
]
