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


class UnauthorizedError(NexusError):
    """The provided credential is missing or invalid."""


class RateLimitExceededError(NexusError):
    """The caller exceeded the allowed request rate."""


class QuotaExceededError(NexusError):
    """A tenant exhausted its configured per-tenant quota."""


class DeploymentError(NexusError):
    """A deployment platform rejected a tool deployment."""


class GoalNotFoundError(NexusError):
    """Requested goal does not exist for this tenant."""

    def __init__(self, goal_id: str) -> None:
        self.goal_id = goal_id
        super().__init__(f"Goal not found: {goal_id}")


class BudgetExhaustedError(NexusError):
    """An autonomous action exceeded its allowed budget."""


class ApprovalRequiredError(NexusError):
    """An autonomous action requires explicit human approval."""


class GoalStatusError(NexusError):
    """A goal was operated on in an invalid lifecycle state."""


class AgentNotFoundError(NexusError):
    """Requested swarm agent does not exist for this tenant."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent not found: {agent_id}")


class SwarmNotFoundError(NexusError):
    """Requested swarm does not exist for this tenant."""

    def __init__(self, swarm_id: str) -> None:
        self.swarm_id = swarm_id
        super().__init__(f"Swarm not found: {swarm_id}")
