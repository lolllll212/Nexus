"""Port contract tests.

Verifies that:
1. All domain ports inherit from ABC and declare their expected abstract methods.
2. In-memory / fake adapters in tests/fakes implement 100% of the port contracts.
3. Subclasses missing required abstract methods cannot be instantiated.
4. Parameter signatures and method names match between ports and their adapters.
"""

from __future__ import annotations

import inspect
from typing import Type

import pytest

from nexus.domain.ports.activity_feed import ActivityFeed
from nexus.domain.ports.auth import Authenticator
from nexus.domain.ports.autonomy import AutonomyPolicy
from nexus.domain.ports.cognition import ActionPolicyStore, CorticalColumnRegistry
from nexus.domain.ports.deployment import DeploymentProvider
from nexus.domain.ports.event_bus import EventBus, EventPublisher, EventSubscriber
from nexus.domain.ports.goal_repository import GoalRepository
from nexus.domain.ports.llm_provider import EmbeddingProvider, LLMProvider, StreamingLLMProvider
from nexus.domain.ports.memory_repository import ConceptRepository, MemoryRepository, ShortTermMemory
from nexus.domain.ports.observability import Metrics, NoopMetrics, NoopTracer, Tracer
from nexus.domain.ports.quota import QuotaService
from nexus.domain.ports.rate_limiter import RateLimiter
from nexus.domain.ports.sandbox import Sandbox
from nexus.domain.ports.secrets import SecretStore
from nexus.domain.ports.speech import SpeechToText, TextToSpeech
from nexus.domain.ports.swarm import AgentRepository, SwarmRepository
from nexus.domain.ports.tool_registry import ToolExecutor, ToolRegistry
from nexus.infrastructure.adapters.auth.api_key_authenticator import ApiKeyAuthenticator
from nexus.infrastructure.adapters.autonomy.goal_repository import InMemoryGoalRepository
from nexus.infrastructure.adapters.autonomy.policy import DefaultAutonomyPolicy
from nexus.infrastructure.adapters.observability.activity_feed import InMemoryActivityFeed
from nexus.infrastructure.adapters.security.quota_service import RateLimitQuota
from nexus.infrastructure.adapters.security.rate_limiter import SlidingWindowRateLimiter
from nexus.infrastructure.adapters.security.secrets import EnvSecretStore
from nexus.infrastructure.adapters.swarm.repositories import (
    InMemoryAgentRepository,
    InMemorySwarmRepository,
)
from tests.fakes import (
    FakeActionPolicyStore,
    FakeConceptRepository,
    FakeCorticalColumnRegistry,
    FakeEmbedder,
    FakeEventBus,
    FakeExecutor,
    FakeLLM,
    FakeMemoryRepository,
    FakeSandbox,
    FakeShortTermMemory,
    FakeSpeechToText,
    FakeTextToSpeech,
    FakeToolRegistry,
)

PORT_ADAPTER_PAIRS: list[tuple[Type, Type]] = [
    (ActivityFeed, InMemoryActivityFeed),
    (Authenticator, ApiKeyAuthenticator),
    (AutonomyPolicy, DefaultAutonomyPolicy),
    (CorticalColumnRegistry, FakeCorticalColumnRegistry),
    (ActionPolicyStore, FakeActionPolicyStore),
    (EventBus, FakeEventBus),
    (EventPublisher, FakeEventBus),
    (EventSubscriber, FakeEventBus),
    (GoalRepository, InMemoryGoalRepository),
    (LLMProvider, FakeLLM),
    (EmbeddingProvider, FakeEmbedder),
    (MemoryRepository, FakeMemoryRepository),
    (ConceptRepository, FakeConceptRepository),
    (ShortTermMemory, FakeShortTermMemory),
    (Tracer, NoopTracer),
    (Metrics, NoopMetrics),
    (QuotaService, RateLimitQuota),
    (RateLimiter, SlidingWindowRateLimiter),
    (Sandbox, FakeSandbox),
    (SecretStore, EnvSecretStore),
    (SpeechToText, FakeSpeechToText),
    (TextToSpeech, FakeTextToSpeech),
    (AgentRepository, InMemoryAgentRepository),
    (SwarmRepository, InMemorySwarmRepository),
    (ToolRegistry, FakeToolRegistry),
    (ToolExecutor, FakeExecutor),
]


@pytest.mark.parametrize("port_cls,adapter_cls", PORT_ADAPTER_PAIRS)
def test_port_abstract_methods_honored_by_adapter(port_cls: Type, adapter_cls: Type):
    """Every abstract method declared by a port must be implemented by its adapter."""
    abstract_methods = getattr(port_cls, "__abstractmethods__", set())

    # Adapter must not have any un-implemented abstract methods
    adapter_abstract = getattr(adapter_cls, "__abstractmethods__", set())
    unimplemented = adapter_abstract.intersection(abstract_methods)
    assert (
        not unimplemented
    ), f"{adapter_cls.__name__} does not implement {unimplemented} from {port_cls.__name__}"

    # Each abstract method must exist on the adapter as a callable
    for method_name in abstract_methods:
        assert hasattr(adapter_cls, method_name), f"{adapter_cls.__name__} missing method {method_name}"
        adapter_attr = getattr(adapter_cls, method_name)
        port_attr = getattr(port_cls, method_name)
        assert callable(adapter_attr) or isinstance(port_attr, property)


@pytest.mark.parametrize("port_cls,adapter_cls", PORT_ADAPTER_PAIRS)
def test_adapter_implements_port_subclass(port_cls: Type, adapter_cls: Type):
    """Adapter must be a subclass of the port abstraction."""
    assert issubclass(adapter_cls, port_cls), f"{adapter_cls.__name__} must inherit from {port_cls.__name__}"


def test_instantiating_abstract_port_raises_type_error():
    """Direct instantiation of any abstract port must fail."""
    abstract_ports = [
        ActivityFeed,
        Authenticator,
        AutonomyPolicy,
        CorticalColumnRegistry,
        ActionPolicyStore,
        DeploymentProvider,
        EventBus,
        EventPublisher,
        EventSubscriber,
        GoalRepository,
        LLMProvider,
        StreamingLLMProvider,
        EmbeddingProvider,
        MemoryRepository,
        ConceptRepository,
        ShortTermMemory,
        Tracer,
        Metrics,
        QuotaService,
        RateLimiter,
        Sandbox,
        SecretStore,
        SpeechToText,
        TextToSpeech,
        AgentRepository,
        SwarmRepository,
        ToolRegistry,
        ToolExecutor,
    ]
    for port in abstract_ports:
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            port()  # type: ignore[abstract]


def test_incomplete_port_subclass_fails_instantiation():
    """A dummy class implementing only a subset of abstract methods must fail instantiation."""

    class IncompleteToolRegistry(ToolRegistry):
        async def register(self, tool):
            pass

        # Omits get, search, list_all, update

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        IncompleteToolRegistry()  # type: ignore[abstract]


def test_streaming_llm_provider_declares_stream():
    """Verify StreamingLLMProvider contract extension over LLMProvider."""
    assert issubclass(StreamingLLMProvider, LLMProvider)
    assert "stream" in StreamingLLMProvider.__abstractmethods__
    assert "complete" in StreamingLLMProvider.__abstractmethods__
    assert "extract_structured" in StreamingLLMProvider.__abstractmethods__


def test_deployment_provider_contract():
    """Verify DeploymentProvider declares deploy, scale, and undeploy."""
    assert "deploy" in DeploymentProvider.__abstractmethods__
    assert "scale" in DeploymentProvider.__abstractmethods__
    assert "undeploy" in DeploymentProvider.__abstractmethods__


def test_port_method_signatures():
    """Verify parameter names match on key port methods."""
    mem_sig = inspect.signature(MemoryRepository.store)
    assert "memory" in mem_sig.parameters
    assert "tenant_id" in mem_sig.parameters

    tool_sig = inspect.signature(ToolExecutor.execute)
    assert "tool_id" in tool_sig.parameters
    assert "params" in tool_sig.parameters


@pytest.mark.asyncio
async def test_llm_provider_default_complete_with_tools_fallback():
    """Verify default complete_with_tools extension fallback for bare LLMProvider subclasses."""

    class MinimalCustomLLMProvider(LLMProvider):
        def __init__(self):
            self.calls = []

        async def complete(
            self,
            messages: list[dict[str, str]],
            temperature: float = 0.7,
            max_tokens: int | None = None,
            tools: list[dict] | None = None,
        ) -> str:
            self.calls.append(
                {
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "tools": tools,
                }
            )
            return "Synthesized result"

        async def extract_structured(self, content, schema, instructions=""):
            return {}

    provider = MinimalCustomLLMProvider()
    original_messages = [
        {"role": "user", "content": "Compute this value"},
    ]
    # Pass a copy to verify caller's input list is not modified in-place
    messages_arg = list(original_messages)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate_pi",
                "description": "Computes digits of pi",
            },
        },
        {
            "type": "function",
            "function": {
                "name": "render_chart",
            },
        },
    ]

    res = await provider.complete_with_tools(
        messages=messages_arg,
        tools=tools,
        temperature=0.2,
        max_tokens=500,
    )

    # 1. Output structure check
    assert res == {"type": "text", "content": "Synthesized result"}

    # 2. Immutability check: caller's input list must NOT be mutated
    assert messages_arg == original_messages
    assert len(messages_arg) == 1

    # 3. Message augmentation check: system message injected with serialized tool schemas
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["temperature"] == 0.2
    assert call["max_tokens"] == 500
    sent_messages = call["messages"]
    assert len(sent_messages) == 2
    assert sent_messages[0]["role"] == "system"
    assert "Available tools:" in sent_messages[0]["content"]
    assert "- calculate_pi: Computes digits of pi" in sent_messages[0]["content"]
    assert "- render_chart:" in sent_messages[0]["content"]
    assert sent_messages[1] == {"role": "user", "content": "Compute this value"}
