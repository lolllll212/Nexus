from __future__ import annotations

from pathlib import Path

from nexus.domain.ports.llm_provider import EmbeddingProvider
from nexus.infrastructure.adapters.persistence.agent_memory_store import AgentMemoryStore


class SemanticFakeEmbedder(EmbeddingProvider):
    def __init__(self) -> None:
        self._dimension = 3

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        lowered = text.lower()
        if "ci" in lowered and ("red" in lowered or "failure" in lowered or "build" in lowered):
            return [1.0, 0.0, 0.0]
        if "redis" in lowered or "cache" in lowered:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


def test_hybrid_memory_rankings_prefer_paraphrases(tmp_path: Path) -> None:
    store = AgentMemoryStore(tmp_path / "memory.json", embedder=SemanticFakeEmbedder(), alpha=0.8)

    relevant = "CI is failing in the build pipeline"
    unrelated = "Redis cache is healthy and stable"
    store.put(agent="xenom", kind="report", text=relevant)
    store.put(agent="xenom", kind="report", text=unrelated)

    results = store.query("CI red on build failure", k=2)

    assert results
    assert results[0][0].text == relevant
    assert all(chunk.text != unrelated for chunk, _ in results[:1])


def test_memory_retrieval_falls_back_to_tfidf_without_embedder(tmp_path: Path) -> None:
    store = AgentMemoryStore(tmp_path / "memory.json")

    relevant = "Docker sandbox timeout on the CI runner"
    unrelated = "The database migration is complete"
    store.put(agent="astra", kind="report", text=relevant)
    store.put(agent="astra", kind="report", text=unrelated)

    results = store.query("docker sandbox timeout ci", k=2)

    assert results
    assert results[0][0].text == relevant
