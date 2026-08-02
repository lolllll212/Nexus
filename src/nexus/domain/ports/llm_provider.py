"""
LLM provider ports.

Swap OpenAI for Llama 3, Anthropic, or a local model by writing a new
adapter - the application layer never changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, List, Optional

from nexus.domain.value_objects.schema import JSONSchema


class LLMProvider(ABC):
    """Abstraction over any chat-completion LLM."""

    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
    ) -> str: ...

    @abstractmethod
    async def extract_structured(
        self,
        content: str,
        schema: JSONSchema,
        instructions: str = "",
    ) -> Dict: ...


class StreamingLLMProvider(LLMProvider):
    """LLM provider capable of token streaming (fast-twitch cortex)."""

    @abstractmethod
    async def stream(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]: ...


class EmbeddingProvider(ABC):
    """Abstraction over embedding models."""

    @abstractmethod
    async def embed(self, text: str) -> List[float]: ...

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...
