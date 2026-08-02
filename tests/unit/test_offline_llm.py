"""
Offline LLM tests (Ollama / LM Studio support).

Proves the OpenAI-compatible adapters and container wiring forward a
configurable `base_url` to the client, without touching the application layer.
A fake `openai` module (installed via sys.modules) records AsyncOpenAI
constructor kwargs, so no network or real OpenAI SDK is needed.
"""

import sys
import types

import pytest

from nexus.infrastructure.adapters.embedding.openai_embedder import OpenAIEmbedder
from nexus.infrastructure.adapters.llm.openai_provider import OpenAIProvider
from nexus.infrastructure.di.container import Config, Container

from tests.fakes.container import FakeContainer


# --------------------------------------------------------------------------- #
#  Fake `openai` module
# --------------------------------------------------------------------------- #

class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeDelta:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChunkChoice:
    def __init__(self, content: str) -> None:
        self.delta = _FakeDelta(content)


class _FakeChunk:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChunkChoice(content)]


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            async def gen():
                for piece in ("streamed ", "answer"):
                    yield _FakeChunk(piece)

            return gen()
        if kwargs.get("response_format"):
            return _FakeResponse('{"entities": []}')
        return _FakeResponse("FINAL ANSWER: ok")


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeEmbeddingDatum:
    def __init__(self, embedding) -> None:
        self.embedding = embedding


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        data = [_FakeEmbeddingDatum([0.1, 0.2, 0.3])] * (len(kwargs["input"]) if isinstance(kwargs["input"], list) else 1)
        return types.SimpleNamespace(data=data)


class _FakeAsyncOpenAI:
    """Records constructor kwargs and returns scripted responses."""

    instances = []

    def __init__(self, **kwargs) -> None:
        _FakeAsyncOpenAI.instances.append(kwargs)
        self.chat = _FakeChat()
        self.embeddings = _FakeEmbeddings()


@pytest.fixture
def fake_openai(monkeypatch):
    module = types.ModuleType("openai")
    module.AsyncOpenAI = _FakeAsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", module)
    _FakeAsyncOpenAI.instances = []
    return _FakeAsyncOpenAI


# --------------------------------------------------------------------------- #
#  OpenAIProvider
# --------------------------------------------------------------------------- #

async def test_provider_forwards_base_url_on_complete(fake_openai):
    provider = OpenAIProvider(api_key="sk-x", base_url="http://localhost:11434/v1")
    out = await provider.complete([{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {}}])
    assert out == "FINAL ANSWER: ok"
    assert fake_openai.instances[-1] == {"api_key": "sk-x", "base_url": "http://localhost:11434/v1"}


async def test_provider_without_base_url_matches_old_behavior(fake_openai):
    provider = OpenAIProvider(api_key="sk-x")
    await provider.complete([{"role": "user", "content": "hi"}])
    assert fake_openai.instances[-1] == {"api_key": "sk-x"}


async def test_provider_empty_api_key_uses_placeholder(fake_openai):
    provider = OpenAIProvider(api_key="", base_url="http://localhost:1234/v1")
    await provider.complete([{"role": "user", "content": "hi"}])
    assert fake_openai.instances[-1]["api_key"] == "local-no-key"


async def test_provider_forwards_base_url_on_extract_structured(fake_openai):
    provider = OpenAIProvider(api_key="sk-x", base_url="http://localhost:11434/v1")
    from nexus.domain.value_objects.schema import JSONSchema

    schema = JSONSchema(type="object", properties={"entities": {"type": "array"}})
    await provider.extract_structured("text", schema)
    assert fake_openai.instances[-1]["base_url"] == "http://localhost:11434/v1"


async def test_provider_forwards_base_url_on_stream(fake_openai):
    provider = OpenAIProvider(api_key="sk-x", base_url="http://localhost:11434/v1")
    chunks = [c async for c in provider.stream([{"role": "user", "content": "hi"}])]
    assert "".join(chunks) == "streamed answer"
    assert fake_openai.instances[-1]["base_url"] == "http://localhost:11434/v1"


# --------------------------------------------------------------------------- #
#  OpenAIEmbedder
# --------------------------------------------------------------------------- #

async def test_embedder_forwards_base_url(fake_openai):
    embedder = OpenAIEmbedder(api_key="sk-x", base_url="http://localhost:11434/v1", dimension=768)
    assert embedder.dimension == 768
    emb = await embedder.embed("hello")
    assert len(emb) == 3
    assert fake_openai.instances[-1] == {"api_key": "sk-x", "base_url": "http://localhost:11434/v1"}


async def test_embedder_forwards_base_url_on_batch(fake_openai):
    embedder = OpenAIEmbedder(api_key="sk-x", base_url="http://localhost:1234/v1")
    out = await embedder.embed_batch(["a", "b"])
    assert len(out) == 2
    assert fake_openai.instances[-1]["base_url"] == "http://localhost:1234/v1"


async def test_embedder_without_base_url_matches_old_behavior(fake_openai):
    embedder = OpenAIEmbedder(api_key="sk-x")
    await embedder.embed("hello")
    assert fake_openai.instances[-1] == {"api_key": "sk-x"}


# --------------------------------------------------------------------------- #
#  Container wiring
# --------------------------------------------------------------------------- #

def test_config_defaults():
    cfg = Config()
    assert cfg.llm_base_url is None
    assert cfg.embedding_base_url is None
    assert cfg.embedding_dimension == 1536


def test_config_reads_offline_env(monkeypatch):
    monkeypatch.setenv("NEXUS_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("NEXUS_EMBEDDING_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("NEXUS_EMBEDDING_DIMENSION", "768")
    cfg = Config()
    assert cfg.llm_base_url == "http://localhost:11434/v1"
    assert cfg.embedding_base_url == "http://localhost:1234/v1"
    assert cfg.embedding_dimension == 768


def test_build_llm_threads_base_url():
    container = object.__new__(Container)
    container.config = Config(llm_base_url="http://localhost:11434/v1")
    llm = container._build_llm()
    assert llm._base_url == "http://localhost:11434/v1"


def test_build_embedder_threads_base_url_and_dimension():
    container = object.__new__(Container)
    container.config = Config(embedding_base_url="http://localhost:11434/v1", embedding_dimension=768)
    embedder = container._build_embedder()
    assert embedder._base_url == "http://localhost:11434/v1"
    assert embedder.dimension == 768


# --------------------------------------------------------------------------- #
#  Hybrid dual-provider split (background LLM slot)
# --------------------------------------------------------------------------- #

def test_config_background_defaults(monkeypatch):
    monkeypatch.delenv("NEXUS_BACKGROUND_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("NEXUS_BACKGROUND_LLM_MODEL", raising=False)
    monkeypatch.delenv("NEXUS_BACKGROUND_LLM_API_KEY", raising=False)
    monkeypatch.setenv("NEXUS_LLM_MODEL", "gpt-4o")
    cfg = Config()
    assert cfg.background_llm_base_url is None
    assert cfg.background_llm_api_key is None
    # Model falls back to the primary LLM model when unset.
    assert cfg.background_llm_model == "gpt-4o"


def test_config_background_reads_env(monkeypatch):
    monkeypatch.setenv("NEXUS_BACKGROUND_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("NEXUS_BACKGROUND_LLM_MODEL", "llama3:8b")
    monkeypatch.setenv("NEXUS_BACKGROUND_LLM_API_KEY", "sk-bg")
    cfg = Config()
    assert cfg.background_llm_base_url == "http://localhost:11434/v1"
    assert cfg.background_llm_model == "llama3:8b"
    assert cfg.background_llm_api_key == "sk-bg"


def test_build_background_llm_uses_own_key():
    container = object.__new__(Container)
    container.config = Config(
        background_llm_base_url="http://localhost:11434/v1",
        background_llm_model="llama3:8b",
        background_llm_api_key="sk-bg",
        openai_api_key="sk-main",
    )
    llm = container._build_background_llm()
    assert llm._base_url == "http://localhost:11434/v1"
    assert llm._model == "llama3:8b"
    assert llm._api_key == "sk-bg"


def test_build_background_llm_falls_back_to_openai_key():
    container = object.__new__(Container)
    container.config = Config(
        background_llm_base_url="http://localhost:11434/v1",
        openai_api_key="sk-main",
    )
    llm = container._build_background_llm()
    assert llm._base_url == "http://localhost:11434/v1"
    assert llm._api_key == "sk-main"


def test_fake_container_splits_primary_and_background_llms():
    fake = FakeContainer()
    assert fake.process_message._llm is fake.llm
    assert fake.background_process_message._llm is fake.background_llm
    assert fake.entity_synthesis._llm is fake.background_llm
    assert fake.pattern_detection._llm is fake.background_llm
    assert fake.dream_session._compression._llm is fake.background_llm
    assert fake.dream_session._simulation._llm is fake.background_llm
    # Interactive path (tool-gen, self-heal) stays on the primary LLM.
    assert fake.tool_generator._llm is fake.llm
    # Autonomy steps run through the background cortex.
    assert fake.autonomy_loop._executor._process_message is fake.background_process_message


async def test_fake_container_subconscious_uses_background_llm():
    fake = FakeContainer()
    fake.background_llm.script = {"extract": {"entities": [{"label": "react", "type": "technology"}]}}
    concepts = await fake.entity_synthesis.synthesize(
        {"message": "react is a library", "session_id": "s1", "active_concepts": []}
    )
    assert concepts and concepts[0].label == "react"
