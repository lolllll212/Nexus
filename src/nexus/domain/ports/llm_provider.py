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
        max_tokens: int | None = None,
        tools: Optional[List[Dict]] = None,
    ) -> str: ...

    async def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Dict:
        """Native function-calling. Returns either:
          {"type": "text", "content": "..."} — final text answer
          {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}} — tool invocation
        Subclasses that support OpenAI function-calling should override this.
        The default falls back to complete() with tool descriptions in the prompt.
        """
        tool_descriptions = "\n".join(
            f"- {t.get('function', {}).get('name', 'unknown')}: {t.get('function', {}).get('description', '')}"
            for t in tools
        )
        augmented = list(messages)
        augmented.insert(0, {"role": "system", "content": f"Available tools:\n{tool_descriptions}"})
        result = await self.complete(augmented, temperature=temperature, max_tokens=max_tokens)
        return {"type": "text", "content": result}

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
        max_tokens: int | None = None,
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
