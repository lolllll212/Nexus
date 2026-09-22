"""In-memory EmbeddingProvider - deterministic, no network.

Produces a fixed-dimension hash-based embedding so the brain runs fully
offline. Not semantically meaningful for vector search, but satisfies the
port so in-memory mode never needs the embedding API.
"""

from __future__ import annotations

import hashlib
from typing import List

from nexus.domain.ports.llm_provider import EmbeddingProvider


class InMemoryEmbedder(EmbeddingProvider):
    def __init__(self, dimension: int = 384) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, text: str) -> List[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [int(b) / 255.0 for b in digest]
        if len(vec) < self._dim:
            vec = (vec * (self._dim // len(vec) + 1))[: self._dim]
        return vec[: self._dim]

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [await self.embed(t) for t in texts]