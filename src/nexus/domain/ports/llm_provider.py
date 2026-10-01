"""
LLM provider ports.

Swap OpenAI for Llama 3, Anthropic, or a local model by writing a new
adapter - the application layer never changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from nexus.domain.value_objects.schema import JSONSchema


class LLMProvider(ABC):
    """Abstraction over any chat-completion LLM.

    Subclasses must implement `complete` and `extract_structured`.
    For function calling, subclasses with native tool support should override `complete_with_tools`.
    Third-party plugin authors or lightweight custom providers may rely on the default
    `complete_with_tools` fallback, which serializes tool schemas into an injected system message
    and invokes `complete` without mutating the caller's message list.
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str: ...

    async def complete_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict:
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
    ) -> dict: ...


class StreamingLLMProvider(LLMProvider):
    """LLM provider capable of token streaming (fast-twitch cortex)."""

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]: ...


class EmbeddingProvider(ABC):
    """Abstraction over embedding models."""

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...
