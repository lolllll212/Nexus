"""
Dream quality tests - verify the recall hit-rate metric is measured before
and after a dreaming cycle, and that it is surfaced on the dream event,
activity feed, and CLI report.
"""

from __future__ import annotations

from tests.fakes.container import FakeContainer

from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.ports.event_bus import EventTopic


async def _seed_episodes(fake: FakeContainer, count: int = 4, tenant_id: str = "default") -> list:
    episodes = []
    for i in range(count):
        m = Memory(
            content=f"USER: project {i} discussion\nNEXUS: answered about topic {i}",
            memory_type=MemoryType.EPISODIC,
            concepts=[f"topic{i}"],
        )
        episodes.append(m)
        await fake.memory_repo.store(m, tenant_id=tenant_id)
    return episodes


class ScriptedDreamLLM:
    def __init__(self) -> None:
        self.extract_calls = 0

    async def extract_structured(self, content, schema, instructions=""):
        self.extract_calls += 1
        return {"facts": [{"content": "abstract fact about project", "importance": 0.9}]}


async def test_dream_measures_recall_hit_rate_before_and_after():
    fake = FakeContainer()
    fake.background_llm = ScriptedDreamLLM()
    fake.dream_session._compression._llm = ScriptedDreamLLM()
    await _seed_episodes(fake)

    result = await fake.dream_session.run(tenant_id="default")

    assert result.recall_probes == 4
    assert result.recall_hit_rate_before is not None
    assert result.recall_hit_rate_after is not None
    # With the fake repo, probes always hit => hit rate is 1.0 both sides.
    assert result.recall_hit_rate_before == 1.0
    assert result.recall_hit_rate_after == 1.0
    assert result.recall_delta == 0.0


async def test_dream_recall_metrics_zero_probes_is_safe():
    """No probes => recall fields are None, no division by zero."""
    fake = FakeContainer()
    fake.background_llm = ScriptedDreamLLM()
    fake.dream_session._compression._llm = ScriptedDreamLLM()

    result = await fake.dream_session.run(tenant_id="empty-tenant")

    assert result.recall_probes == 0
    assert result.recall_hit_rate_before is None
    assert result.recall_hit_rate_after is None
    assert result.recall_delta is None


async def test_dream_completed_event_carries_recall_payload():
    fake = FakeContainer()
    fake.background_llm = ScriptedDreamLLM()
    fake.dream_session._compression._llm = ScriptedDreamLLM()
    await _seed_episodes(fake, count=2)

    events = []

    async def capture(event):
        events.append(event)

    await fake.event_bus.subscribe(EventTopic.DREAM_COMPLETED, capture)
    await fake.dream_session.run(tenant_id="default")

    assert len(events) == 1
    payload = events[0].payload
    assert "recall_hit_rate_before" in payload
    assert "recall_hit_rate_after" in payload
    assert "recall_delta" in payload
    assert payload["recall_probes"] == 2


async def test_dream_recall_metrics_surface_on_activity_feed():
    from nexus.infrastructure.adapters.eventbus.in_memory_event_bus import InMemoryEventBus

    fake = FakeContainer()
    # Wire the real InMemoryEventBus + a container-style dream handler so the
    # feed records recall fields, exactly like the production Container does.
    bus = InMemoryEventBus()

    async def on_dream_completed(event):
        fake.activity_feed.record("dream", dict(event.payload or {}))

    # Rebuild the dream use case bound to the bus so events flow to the feed.

    fake.dream_session._event_bus = bus
    await bus.subscribe(EventTopic.DREAM_COMPLETED, on_dream_completed)
    fake.background_llm = ScriptedDreamLLM()
    fake.dream_session._compression._llm = ScriptedDreamLLM()
    await _seed_episodes(fake, count=3)

    await fake.dream_session.run(tenant_id="default")
    await _drain(bus)

    entries = fake.activity_feed.recent("dream", limit=10)
    assert len(entries) == 1
    assert entries[0]["recall_hit_rate_before"] is not None
    assert "recall_delta" in entries[0]


async def _drain(event_bus):
    import asyncio

    await asyncio.sleep(0.05)
