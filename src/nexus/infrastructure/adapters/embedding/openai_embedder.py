"""OpenAI-compatible embedding provider adapter (works with Ollama / LM Studio)."""

from __future__ import annotations

from typing import List, Optional

from nexus.domain.ports.llm_provider import EmbeddingProvider


class OpenAIEmbedder(EmbeddingProvider):
    """Text embedding via an OpenAI-compatible embeddings API.

    `base_url` points at a local server (e.g. Ollama's `/v1`); when None the
    client talks to real OpenAI. `dimension` must match the served model -
    local embedding models like `nomic-embed-text` output 768 dims, not
    OpenAI's 1536, and Qdrant's collection is created from this value.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-large",
        dimension: int = 1536,
        base_url: Optional[str] = None,
    ) -> None:
        # Local servers don't check the key; accept any value.
        self._api_key = api_key or "local-no-key"
        self._model = model
        self._dim = dimension
        self._base_url = base_url

    @property
    def dimension(self) -> int:
        return self._dim

    def _client(self):
        from openai import AsyncOpenAI

        if self._base_url:
            return AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return AsyncOpenAI(api_key=self._api_key)

    async def embed(self, text: str) -> List[float]:
        client = self._client()
        resp = await client.embeddings.create(model=self._model, input=text)
        return resp.data[0].embedding

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        client = self._client()
        resp = await client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]
