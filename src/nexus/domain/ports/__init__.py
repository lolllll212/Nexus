"""
NEXUS Ports - the interfaces that decouple domain/application from infrastructure.

These are the "ports" of Hexagonal (Ports & Adapters) architecture.
The application depends ONLY on these abstractions, never on concrete
implementations. Swapping Redis for Kafka, OpenAI for Llama, or Neo4j for
a different graph DB requires writing a new adapter - zero changes to the brain.
"""

from nexus.domain.ports.deployment import DeploymentProvider
from nexus.domain.ports.event_bus import Event, EventBus, EventPublisher, EventSubscriber
from nexus.domain.ports.execution import ToolExecutor
from nexus.domain.ports.llm_provider import EmbeddingProvider, LLMProvider, StreamingLLMProvider
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository, ShortTermMemory
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.swarm_state import SwarmStatePort
from nexus.domain.ports.tool_registry import ToolRegistry

__all__ = [
    "ConceptRepository",
    "DeploymentProvider",
    "EmbeddingProvider",
    "Event",
    "EventBus",
    "EventPublisher",
    "EventSubscriber",
    "LLMProvider",
    "MemoryRepository",
    "Sandbox",
    "ShortTermMemory",
    "StreamingLLMProvider",
    "SwarmStatePort",
    "ToolExecutor",
    "ToolRegistry",
]
