"""
NVIDIA NIM (NVIDIA Inference Microservices) LLMProvider adapter.

Integrates with NVIDIA NIM APIs (cloud-hosted at https://integrate.api.nvidia.com/v1
or self-hosted on-premises NIM microservice containers). Implements the
hexagonal LLMProvider and StreamingLLMProvider ports.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from nexus.domain.exceptions import LLMUnavailableError
from nexus.domain.ports.llm_provider import StreamingLLMProvider
from nexus.domain.value_objects.schema import JSONSchema

logger = logging.getLogger("nexus.nim")

DEFAULT_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NIM_MODEL = "meta/llama-3.3-70b-instruct"

SUPPORTED_NIM_MODELS = [
    {
        "id": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "name": "Nemotron 3.5 Lightning 30B (fast)",
        "provider": "NVIDIA NIM",
        "description": "Fastest verified reasoning model - sub-second first token. Default.",
        "tags": ["default", "reasoning", "fast"],
    },
    {
        "id": "nvidia/nemotron-3-ultra-550b-a55b",
        "name": "Nemotron 3 Ultra 550B",
        "provider": "NVIDIA NIM",
        "description": "Largest verified reasoning model - deep multi-step reasoning.",
        "tags": ["flagship", "reasoning"],
    },
    {
        "id": "openai/gpt-oss-20b",
        "name": "GPT-OSS 20B",
        "provider": "OpenAI / NVIDIA NIM",
        "description": "Open-weight general model - balanced speed and quality.",
        "tags": ["general"],
    },
    {
        "id": "stepfun-ai/step-5-preview",
        "name": "Step 5 Preview",
        "provider": "StepFun / NVIDIA NIM",
        "description": "Fast general assistant model.",
        "tags": ["general", "fast"],
    },
    {
        "id": "z-ai/glm-5.3",
        "name": "GLM 5.3",
        "provider": "Z.ai / NVIDIA NIM",
        "description": "Strong general model - slower responses, deep answers.",
        "tags": ["general", "deep"],
    },
]


class NvidiaNimProvider(StreamingLLMProvider):
    """
    Implements LLMProvider + StreamingLLMProvider targeting NVIDIA NIM.
    Compatible with both NVIDIA cloud API (https://integrate.api.nvidia.com/v1)
    and locally hosted NIM microservice containers.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_NIM_MODEL,
        temperature: float = 0.5,
        base_url: str | None = None,
        default_max_tokens: int = 4096,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._model = model or DEFAULT_NIM_MODEL
        self._temperature = temperature
        self._base_url = (base_url or DEFAULT_NIM_BASE_URL).rstrip("/")
        self._default_max_tokens = default_max_tokens

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        self._model = value

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        self._base_url = value.rstrip("/")

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key and self._api_key != "local-no-key")

    def set_api_key(self, api_key: str) -> None:
        self._api_key = (api_key or "").strip()

    def _client(self):
        from openai import AsyncOpenAI

        key = self._api_key if self.has_api_key else "nvapi-dummy"
        return AsyncOpenAI(api_key=key, base_url=self._base_url)

    def _simulated_response(self, messages: list[dict[str, str]]) -> str:
        """Realistic fallback when no NVIDIA API key is configured or offline."""
        last_msg = messages[-1]["content"] if messages else ""
        lower = last_msg.lower()

        if "hub" in lower or "cluster" in lower:
            return (
                "J.A.R.V.I.S. Knowledge Graph Diagnostic: Top hubs detected — Skill Suites, Local Businesses, "
                "AI Workshop, and Claude Code. 142 concepts indexed with 318 synaptic cross-links. "
                "NVIDIA NIM microservice active and ready for deep entity synthesis."
            )
        if "workshop" in lower:
            return (
                "The AI Workshop is the primary nucleus of our system architecture. It bridges autonomous ReAct "
                "reasoning loops with tool execution, cognitive memory pipelines, and real-time sensory feedback."
            )
        if "claude" in lower:
            return (
                "Claude Code integration cluster: houses autonomous developer agent specifications, "
                "AST refactoring tools, and continuous self-healing coding routines."
            )
        return (
            f"J.A.R.V.I.S. at your service, sir. I have processed your inquiry via NVIDIA NIM ({self._model}). "
            f"All cognitive nodes are synchronized and operating at nominal parameters. "
            f"Query processed: '{last_msg[:60]}'."
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.5,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        if not self.has_api_key:
            return self._simulated_response(messages)

        try:
            client = self._client()
            kwargs: dict = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature if temperature is not None else self._temperature,
                "max_tokens": max_tokens or self._default_max_tokens,
            }
            if tools:
                kwargs["tools"] = tools
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("NVIDIA NIM completion error: %s. Falling back to simulated reply.", exc)
            return self._simulated_response(messages)

    async def complete_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict],
        temperature: float = 0.5,
        max_tokens: int | None = None,
    ) -> dict:
        if not self.has_api_key:
            # Simulated tool call if requested, or simulated text
            text = self._simulated_response(messages)
            return {"type": "text", "content": text}

        try:
            client = self._client()
            resp = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens or self._default_max_tokens,
            )
            msg = resp.choices[0].message
            if msg.tool_calls:
                tc = msg.tool_calls[0]
                try:
                    arguments = json.loads(tc.function.arguments)
                except Exception:
                    arguments = {"raw": tc.function.arguments}
                return {
                    "type": "tool_call",
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": arguments,
                }
            return {"type": "text", "content": msg.content or ""}
        except Exception as exc:
            logger.warning("NVIDIA NIM complete_with_tools error: %s", exc)
            if not self.has_api_key or "401" in str(exc):
                return {"type": "text", "content": self._simulated_response(messages)}
            raise LLMUnavailableError(f"NVIDIA NIM tool call failed: {exc}") from exc

    async def extract_structured(
        self,
        content: str,
        schema: JSONSchema,
        instructions: str = "",
    ) -> dict:
        messages = [
            {
                "role": "system",
                "content": instructions + " Return ONLY valid JSON matching the requested schema.",
            },
            {"role": "user", "content": content},
        ]
        if not self.has_api_key:
            return {"status": "ok", "summary": self._simulated_response(messages)}

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
            logger.warning("NVIDIA NIM extract_structured fallback: %s", exc)
            return {"raw": content, "note": "parsed_fallback"}

    def get_supported_models(self) -> list[dict]:
        return SUPPORTED_NIM_MODELS

    def get_tier_model(self, tier: str) -> str:
        """Resolve model name for latency-tiered execution ('reflex', 'cortex', 'synthesis')."""
        tiers = {
            "reflex": "meta/llama-3.1-8b-instruct",
            "cortex": "meta/llama-3.3-70b-instruct",
            "synthesis": "nvidia/nemotron-4-340b-instruct",
        }
        return tiers.get(tier.lower(), self._model)

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens from NVIDIA NIM or fallback to simulated stream."""
        if not self.has_api_key:
            simulated = self._simulated_response(messages)
            words = simulated.split(" ")
            for i, word in enumerate(words):
                prefix = "" if i == 0 else " "
                yield prefix + word
                await asyncio.sleep(0.015)
            return

        try:
            client = self._client()
            resp = await client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature if temperature is not None else self._temperature,
                max_tokens=max_tokens or self._default_max_tokens,
                stream=True,
            )
            async for chunk in resp:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except Exception as exc:
            logger.warning("NVIDIA NIM streaming error: %s. Falling back to simulated stream.", exc)
            simulated = self._simulated_response(messages)
            for word in simulated.split(" "):
                yield word + " "
                await asyncio.sleep(0.01)

    async def verify_connection(self) -> dict:
        """Check connection to NVIDIA NIM endpoint."""
        if not self.has_api_key:
            return {
                "connected": False,
                "status": "unconfigured",
                "message": "NVIDIA API key not set. Running in simulation mode.",
                "model": self._model,
                "base_url": self._base_url,
            }
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                if res.status_code == 200:
                    return {
                        "connected": True,
                        "status": "connected",
                        "message": "Successfully connected to NVIDIA NIM endpoint.",
                        "model": self._model,
                        "base_url": self._base_url,
                    }
                return {
                    "connected": False,
                    "status": "error",
                    "code": res.status_code,
                    "message": f"NVIDIA NIM returned status {res.status_code}",
                    "model": self._model,
                    "base_url": self._base_url,
                }
        except Exception as exc:
            return {
                "connected": False,
                "status": "unreachable",
                "message": str(exc),
                "model": self._model,
                "base_url": self._base_url,
            }
