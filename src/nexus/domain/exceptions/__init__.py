"""Domain exceptions - typed failures that keep layers decoupled."""

from __future__ import annotations


class NexusError(Exception):
    """Base class for all NEXUS domain errors."""


class ToolNotFoundError(NexusError):
    """Requested tool does not exist in the registry."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(f"Tool not found: {tool_id}")


class ToolGenerationError(NexusError):
    """A tool failed to generate or pass its tests."""


class MemoryNotFoundError(NexusError):
    """Requested memory or concept does not exist."""


class ConceptNotFoundError(MemoryNotFoundError):
    """Requested concept does not exist in the graph."""


class LLMUnavailableError(NexusError):
    """The LLM provider is unreachable or returned an error."""


class ContextWindowExceededError(NexusError):
    """Working context exceeded the model's window."""


class InvalidToolCallError(NexusError):
    """The model produced a malformed tool invocation."""
