"""
Tests for NVIDIA NIM LLMProvider adapter and API endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from nexus.infrastructure.adapters.llm.nvidia_nim_provider import (
    DEFAULT_NIM_BASE_URL,
    DEFAULT_NIM_MODEL,
    NvidiaNimProvider,
)
from nexus.infrastructure.api.main import create_app
from tests.fakes.container import TEST_API_KEY_1


def test_nvidia_nim_provider_initialization():
    provider = NvidiaNimProvider(api_key="nvapi-test12345")
    assert provider.has_api_key is True
    assert provider.model == DEFAULT_NIM_MODEL
    assert provider.base_url == DEFAULT_NIM_BASE_URL
    assert len(provider.get_supported_models()) > 0


def test_nvidia_nim_provider_simulated_when_no_key():
    provider = NvidiaNimProvider(api_key="")
    assert provider.has_api_key is False


@pytest.mark.asyncio
async def test_nvidia_nim_complete_simulated():
    provider = NvidiaNimProvider(api_key="")
    reply = await provider.complete([{"role": "user", "content": "Tell me about the AI Workshop hub"}])
    assert "AI Workshop" in reply
    assert "J.A.R.V.I.S." in reply or "nucleus" in reply


@pytest.mark.asyncio
async def test_nvidia_nim_complete_with_mocked_client():
    provider = NvidiaNimProvider(api_key="nvapi-real-key-12345")

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "NVIDIA NIM response from Llama 3.3"

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch.object(provider, "_client", return_value=mock_client):
        res = await provider.complete([{"role": "user", "content": "Hello NIM"}])
        assert res == "NVIDIA NIM response from Llama 3.3"
        mock_client.chat.completions.create.assert_called_once()


@pytest.mark.asyncio
async def test_nvidia_nim_complete_with_tools_mocked():
    provider = NvidiaNimProvider(api_key="nvapi-real-key-12345")

    mock_tc = MagicMock()
    mock_tc.id = "call_abc"
    mock_tc.function.name = "web_search"
    mock_tc.function.arguments = '{"query": "NVIDIA NIM"}'

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.tool_calls = [mock_tc]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch.object(provider, "_client", return_value=mock_client):
        res = await provider.complete_with_tools(
            [{"role": "user", "content": "Search for NIM"}],
            tools=[{"type": "function", "function": {"name": "web_search"}}],
        )
        assert res["type"] == "tool_call"
        assert res["name"] == "web_search"
        assert res["arguments"] == {"query": "NVIDIA NIM"}


@pytest.mark.asyncio
async def test_nvidia_nim_streaming_simulation():
    provider = NvidiaNimProvider(api_key="")
    chunks = []
    async for chunk in provider.stream([{"role": "user", "content": "Status report"}]):
        chunks.append(chunk)
    full_text = "".join(chunks)
    assert len(full_text) > 0
    assert "J.A.R.V.I.S." in full_text


def test_nim_api_routes():
    from tests.fakes.container import FakeContainer

    app = create_app()
    fake = FakeContainer()
    app.state.container = fake
    client = TestClient(app, headers={"Authorization": f"Bearer {TEST_API_KEY_1}"})

    # Status endpoint
    res = client.get("/api/nim/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert "active_model" in data
    assert "supported_models" in data
    assert len(data["supported_models"]) >= 5

    # Models endpoint
    res_models = client.get("/api/nim/models")
    assert res_models.status_code == 200
    assert len(res_models.json()["models"]) >= 5

    # Chat endpoint
    res_chat = client.post(
        "/api/nim/chat",
        json={"prompt": "Analyze knowledge graph hubs", "temperature": 0.3},
    )
    assert res_chat.status_code == 200
    chat_data = res_chat.json()
    assert "response" in chat_data
    assert chat_data["provider"] == "nvidia_nim"
    assert len(chat_data["response"]) > 0

    # Configure endpoint
    res_cfg = client.post(
        "/api/nim/configure",
        json={
            "model": "nvidia/llama-3.1-nemotron-70b-instruct",
            "api_key": "nvapi-new-key-xyz",
        },
    )
    assert res_cfg.status_code == 200
    cfg_data = res_cfg.json()
    assert cfg_data["active_model"] == "nvidia/llama-3.1-nemotron-70b-instruct"
    assert cfg_data["has_api_key"] is True
