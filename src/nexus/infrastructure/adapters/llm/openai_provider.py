"""
OpenAI LLMProvider adapter.

Swap to Anthropic or Llama by writing a new adapter class that implements
the same port - the application layer never changes.
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Dict, List, Optional

from nexus.domain.exceptions import LLMUnavailableError
from nexus.domain.ports.llm_provider import LLMProvider, StreamingLLMProvider
from nexus.domain.value_objects.schema import JSONSchema


class OpenAIProvider(StreamingLLMProvider):
    """Implements LLMProvider + StreamingLLMProvider via the OpenAI API."""

    def __init__(self, api_key: str, model: str = "gpt-4o", temperature: float = 0.7) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature

    async def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: Optional[List[Dict]] = None,
    ) -> str:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._api_key)
            kwargs: dict = {"model": self._model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            if tools:
                kwargs["tools"] = tools
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

    async def extract_structured(self, content: str, schema: JSONSchema, instructions: str = "") -> Dict:
        """Force JSON output matching the schema via the structured-output path."""
        messages = [
            {"role": "system", "content": instructions + " Return ONLY valid JSON."},
            {"role": "user", "content": content},
        ]
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._api_key)
            resp = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            return json.loads(text)
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

    async def stream(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 4096) -> AsyncGenerator[str, None]:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._api_key)
            stream = await client.chat.completions.create(
                model=self._model, messages=messages, temperature=temperature, max_tokens=max_tokens, stream=True
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc
