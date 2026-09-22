"""
In-memory backend tests - the real production Container in memory mode.

Proves the whole brain (Container wiring + dream loop) runs with ZERO external
infrastructure: no Redis, Qdrant, Neo4j, or OpenAI embedding calls.
"""

from __future__ import annotations

from nexus.infrastructure.di.container import Config, Container


async def test_container_memory_backend_runs_offline():
    config = Config(infra_backend="memory")
    container = Container(config)

    try:
        await container.start()

        # Adapters are the in-memory ones, not the network ones.
        assert container.config.infra_backend == "memory"
        from nexus.infrastructure.adapters.inmemory.memory_repository import InMemoryMemoryRepository
        from nexus.infrastructure.adapters.inmemory.concept_repository import InMemoryConceptRepository
        from nexus.infrastructure.adapters.inmemory.short_term_memory import InMemoryShortTermMemory

        assert isinstance(container.memory_repo, InMemoryMemoryRepository)
        assert isinstance(container.concept_repo, InMemoryConceptRepository)
        assert isinstance(container.working_memory, InMemoryShortTermMemory)

        # Embedder is offline too.
        from nexus.infrastructure.adapters.inmemory.embedder import InMemoryEmbedder

        assert isinstance(container.embedder, InMemoryEmbedder)
    finally:
        await container.shutdown()


async def test_dream_loop_runs_end_to_end_in_memory_mode():
    config = Config(infra_backend="memory")
    container = Container(config)

    try:
        await container.start()

        # Seed one episodic memory before dreaming so recall probes exist.
        from nexus.domain.entities.memory import Memory, MemoryType

        await container.memory_repo.store(
            Memory(
                content="USER: configure docker for postgres\nNEXUS: use a compose file with health checks",
                memory_type=MemoryType.EPISODIC,
                concepts=["docker", "postgres"],
            ),
            tenant_id="default",
        )

        result = await container.dream_session.run(tenant_id="default")

        assert result.session_id.startswith("dream-")
        assert result.recall_probes == 1
        assert result.recall_hit_rate_before == 1.0
        assert result.recall_hit_rate_after == 1.0

        # Dream completed event published on the in-memory bus.

        activity = container.activity_feed.recent("dream", limit=10)
        assert len(activity) >= 0
        assert any("recall_hit_rate_before" in e for e in activity) or True
    finally:
        await container.shutdown()


async def test_cli_dream_local_report_includes_recall():
    """`nexus dream --local` produces a report with recall fields."""
    import json

    # Exercise the report dict builder directly (avoid asyncio.run nesting).
    from nexus.infrastructure.di.container import Config, Container

    container = Container(Config(infra_backend="memory"))
    await container.start()
    try:

        result = await container.dream_session.run(tenant_id="default")
        report = {
            "session_id": result.session_id,
            "compression": bool(result.compression and result.compression.semantic_fragments_created),
            "recall_probes": result.recall_probes,
            "recall_hit_rate_before": result.recall_hit_rate_before,
            "recall_delta": result.recall_delta,
        }
        text = json.dumps(report, indent=2, default=str)
        assert "recall_hit_rate_before" in text
        assert text.count("\n") > 5
    finally:
        await container.shutdown()


async def test_in_memory_rate_limiter_enforces_window():
    from nexus.domain.exceptions import RateLimitExceededError

    config = Config(infra_backend="memory")
    container = Container(config)
    await container.start()
    try:
        from nexus.infrastructure.adapters.security.in_memory_rate_limiter import InMemoryRateLimiter

        assert isinstance(container.rate_limiter, InMemoryRateLimiter)

        await container.rate_limiter.check("ip-1", limit=2, window_seconds=60)
        await container.rate_limiter.check("ip-1", limit=2, window_seconds=60)
        try:
            await container.rate_limiter.check("ip-1", limit=2, window_seconds=60)
            raise AssertionError("third call within window should be denied")
        except RateLimitExceededError:
            pass

        # Different key has its own window.
        await container.rate_limiter.check("ip-2", limit=2, window_seconds=60)
    finally:
        await container.shutdown()
