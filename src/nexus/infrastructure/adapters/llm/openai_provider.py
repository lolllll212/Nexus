"""
OpenAI LLMProvider adapter.

Swap to Anthropic or Llama by writing a new adapter class that implements
the same port - the application layer never changes. This adapter also speaks
to any OpenAI-compatible endpoint (Ollama, LM Studio, etc.) by passing an
optional `base_url` - a pure config change, no new adapter required.
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Dict, List, Optional

from nexus.domain.exceptions import LLMUnavailableError
from nexus.domain.ports.llm_provider import StreamingLLMProvider
from nexus.domain.value_objects.schema import JSONSchema


class OpenAIProvider(StreamingLLMProvider):
    """Implements LLMProvider + StreamingLLMProvider via an OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        temperature: float = 0.7,
        base_url: Optional[str] = None,
        default_max_tokens: int = 8192,
    ) -> None:
        # Local servers (Ollama / LM Studio) don't check the key; accept any value.
        self._api_key = api_key or "local-no-key"
        self._model = model
        self._temperature = temperature
        self._base_url = base_url
        self._default_max_tokens = default_max_tokens

    def _client(self):
        from openai import AsyncOpenAI

        if self._base_url:
            return AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return AsyncOpenAI(api_key=self._api_key)

    async def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: Optional[List[Dict]] = None,
    ) -> str:
        try:
            client = self._client()
            kwargs: dict = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens or self._default_max_tokens,
            }
            if tools:
                kwargs["tools"] = tools
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

    async def complete_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> Dict:
        """Native OpenAI function-calling. Returns structured tool call or text."""
        try:
            client = self._client()
            resp = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens or self._default_max_tokens,
            )
            msg = resp.choices[0].message

            # Model chose to call a tool
            if msg.tool_calls:
                tc = msg.tool_calls[0]
                return {
                    "type": "tool_call",
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }

            # Model returned a text answer
            return {"type": "text", "content": msg.content or ""}
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

    async def extract_structured(self, content: str, schema: JSONSchema, instructions: str = "") -> Dict:
        """Force JSON output matching the schema via the structured-output path."""
        # NOTE: `response_format={"type": "json_object"}` is not reliably
        # supported by every local model (Ollama / LM Studio). This is a known
        # limitation to flag, not something to work around in this adapter.
        messages = [
            {"role": "system", "content": instructions + " Return ONLY valid JSON."},
            {"role": "user", "content": content},
        ]
        try:
            client = self._client()
            resp = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            return json.loads(text)
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

    async def stream(
        self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int | None = None
    ) -> AsyncGenerator[str, None]:
        try:
            client = self._client()
            stream = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens or self._default_max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc
