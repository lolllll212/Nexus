"""OpenAI embedding provider adapter."""

from __future__ import annotations

from typing import List

from nexus.domain.ports.llm_provider import EmbeddingProvider


class OpenAIEmbedder(EmbeddingProvider):
    """Text embedding via OpenAI's embeddings API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-large", dimension: int = 1536) -> None:
        self._api_key = api_key
        self._model = model
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, text: str) -> List[float]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key)
        resp = await client.embeddings.create(model=self._model, input=text)
        return resp.data[0].embedding

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key)
        resp = await client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]
