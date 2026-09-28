"""LLM provider adapters - OpenAI, NVIDIA NIM, Anthropic, local models."""

from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider
from nexus.infrastructure.adapters.llm.nvidia_nim_provider import NvidiaNimProvider

__all__ = ["OpenAIProvider", "NvidiaNimProvider"]
