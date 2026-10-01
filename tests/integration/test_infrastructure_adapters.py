from __future__ import annotations

import asyncio

import pytest

from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.exceptions import RateLimitExceededError, UnauthorizedError
from nexus.domain.ports.event_bus import Event, EventTopic
from nexus.infrastructure.adapters.auth.api_key_authenticator import ApiKeyAuthenticator
from nexus.infrastructure.adapters.eventbus.in_memory_event_bus import InMemoryEventBus
from nexus.infrastructure.adapters.inmemory.concept_repository import InMemoryConceptRepository
from nexus.infrastructure.adapters.inmemory.embedder import InMemoryEmbedder
from nexus.infrastructure.adapters.inmemory.memory_repository import InMemoryMemoryRepository
from nexus.infrastructure.adapters.inmemory.short_term_memory import InMemoryShortTermMemory
from nexus.infrastructure.adapters.security.in_memory_rate_limiter import InMemoryRateLimiter
from nexus.infrastructure.di.container import Config, Container


@pytest.fixture
def memory_container(monkeypatch: pytest.MonkeyPatch) -> Container:
    monkeypatch.setenv("NEXUS_INFRA_BACKEND", "memory")
    monkeypatch.setenv(
        "NEXUS_API_KEYS",
        '{"integration-key":{"user_id":"integration-user","tenant_id":"integration-tenant","role":"user"}}',
    )
    return Container(Config(infra_backend="memory"))


@pytest.mark.asyncio
async def test_memory_backend_adapters_satisfy_port_contracts(memory_container: Container) -> None:
    container = memory_container
    assert isinstance(container.event_bus, InMemoryEventBus)
    assert isinstance(container.embedder, InMemoryEmbedder)
    assert isinstance(container.memory_repo, InMemoryMemoryRepository)
    assert isinstance(container.concept_repo, InMemoryConceptRepository)
    assert isinstance(container.working_memory, InMemoryShortTermMemory)
    assert isinstance(container.rate_limiter, InMemoryRateLimiter)

    vector = await container.embedder.embed("offline adapter contract")
    assert len(vector) == container.embedder.dimension
    assert all(0.0 <= item <= 1.0 for item in vector)

    memory = Memory(content="adapter contract memory", memory_type=MemoryType.SEMANTIC)
    await container.memory_repo.store(memory, tenant_id="integration-tenant")
    assert await container.memory_repo.retrieve("adapter contract", tenant_id="integration-tenant") == [
        memory
    ]
    assert await container.memory_repo.retrieve("adapter contract", tenant_id="another-tenant") == []

    concept = await container.concept_repo.get_or_create("Adapter", "test", tenant_id="integration-tenant")
    assert await container.concept_repo.get(concept.id, tenant_id="integration-tenant") == concept
    assert await container.concept_repo.get(concept.id, tenant_id="another-tenant") is None

    await container.working_memory.set("contract", {"ok": True}, ttl_seconds=60)
    assert await container.working_memory.get("contract") == {"ok": True}
    await container.working_memory.delete("contract")
    assert await container.working_memory.get("contract") is None

    received: list[Event] = []

    async def receive(event: Event) -> None:
        received.append(event)

    await container.event_bus.subscribe(EventTopic.USER_MESSAGE, receive)
    await container.event_bus.publish(Event(topic=EventTopic.USER_MESSAGE, payload={"message": "contract"}))
    await asyncio.sleep(0)
    assert received and received[0].payload["message"] == "contract"

    await container.rate_limiter.check("contract", limit=1, window_seconds=60)
    with pytest.raises(RateLimitExceededError):
        await container.rate_limiter.check("contract", limit=1, window_seconds=60)


@pytest.mark.asyncio
async def test_auth_and_tool_executor_contracts_are_offline(memory_container: Container) -> None:
    container = memory_container
    assert isinstance(container.authenticator, ApiKeyAuthenticator)
    identity = await container.authenticator.authenticate("integration-key")
    assert identity.user_id == "integration-user"
    with pytest.raises(UnauthorizedError):
        await container.authenticator.authenticate("invalid-key")

    result = await container.executor.execute("calculator", {"expression": "2 + 2"})
    assert result.get("result") == 4
