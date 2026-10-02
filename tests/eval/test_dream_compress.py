"""Tests for DreamPhase 1: `CompressionUseCase` (episodic -> semantic consolidation).

`compress.py` was untested. Writing the tests turned up a real defect, pinned by
a test below:

* The flag-everything loop ran AFTER the batch loop and flagged ALL episodes as
  `consolidated`, including episodes whose LLM batch had FAILED. An episode that
  was never distilled but got marked done is silent knowledge loss: the adapter
  cold-stores it and its content is never compressed.

Tests live in `tests/eval/` because `tests/unit/` belongs to Tron
(docs/AGENT_COORDINATION.md) and the application layer is mine.
"""

from __future__ import annotations

from typing import Any

from nexus.application.subcortex.dreaming.compress import CompressionUseCase
from nexus.domain.entities.memory import Memory, MemoryType
from nexus.domain.value_objects.schema import JSONSchema
from tests.fakes import FakeMemoryRepository

_SCHEMA = JSONSchema(
    type="object",
    properties={"facts": {"type": "array", "items": {"type": "object"}}},
    required=["facts"],
)


class _ScriptedExtractor:
    """LLM fake whose responses are popped per call, so batches can diverge."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def extract_structured(self, content: str, schema: JSONSchema, instructions: str = "") -> dict:
        self.calls.append(content)
        outcome = self._responses.pop(0) if self._responses else {"facts": []}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def complete(self, *args: Any, **kwargs: Any) -> str:  # pragma: no cover - unused here
        return "FINAL ANSWER: unused"


def _episode(text: str) -> Memory:
    return Memory(content=text, memory_type=MemoryType.EPISODIC, concepts=[], metadata={})


def _facts(*contents: str, importance: float | None = None) -> dict:
    items = [
        {"content": c, **({"importance": importance} if importance is not None else {})} for c in contents
    ]
    return {"facts": items}


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


async def test_run_distills_episodes_into_semantic_memories():
    llm = _ScriptedExtractor([_facts("prefers dark mode", "uses pytest", importance=0.8)])
    repo = FakeMemoryRepository()
    episodes = [_episode("user said they like dark themes"), _episode("user mentioned pytest")]

    result = await CompressionUseCase(llm, repo).run(episodes)  # type: ignore[arg-type]

    assert (result.episodes_processed, result.semantic_fragments_created, result.raw_transcripts_stored) == (
        2,
        2,
        2,
    )
    stored = list(repo.memories.values())
    assert len(stored) == 2
    assert all(m.memory_type == MemoryType.SEMANTIC for m in stored)
    assert all(m.metadata["origin"] == "dream_compression" for m in stored)
    assert all(m.metadata["importance"] == 0.8 for m in stored)
    assert all(e.consolidated is True for e in episodes)


async def test_importance_defaults_to_half_when_the_llm_omits_it():
    llm = _ScriptedExtractor([_facts("a fact without importance")])
    repo = FakeMemoryRepository()

    result = await CompressionUseCase(llm, repo).run([_episode("some transcript")])  # type: ignore[arg-type]

    stored = list(repo.memories.values())
    assert result.semantic_fragments_created == 1
    assert stored[0].metadata["importance"] == 0.5


async def test_tenant_id_is_passed_through_to_the_store():
    llm = _ScriptedExtractor([_facts("fact for tenant two")])
    repo = FakeMemoryRepository()

    await CompressionUseCase(llm, repo).run([_episode("transcript")], tenant_id="t2")  # type: ignore[arg-type]

    stored_id = next(iter(repo.memories))
    assert repo._tenant[stored_id] == "t2"


async def test_transcripts_are_joined_with_a_separator_per_batch():
    llm = _ScriptedExtractor([_facts("one fact")])
    repo = FakeMemoryRepository()

    await CompressionUseCase(llm, repo).run([_episode("first"), _episode("second")])  # type: ignore[arg-type]

    assert llm.calls == ["first\n---\nsecond"]


# --------------------------------------------------------------------------
# Batching
# --------------------------------------------------------------------------


async def test_batch_size_controls_how_many_llm_calls_run():
    episodes = [_episode(f"transcript {i}") for i in range(4)]

    one_llm = _ScriptedExtractor([_facts("f"), _facts("f"), _facts("f"), _facts("f")])
    await CompressionUseCase(one_llm, FakeMemoryRepository()).run(episodes, batch_size=1)  # type: ignore[arg-type]
    assert len(one_llm.calls) == 4

    big_llm = _ScriptedExtractor([_facts("f")])
    await CompressionUseCase(big_llm, FakeMemoryRepository()).run(episodes, batch_size=50)  # type: ignore[arg-type]
    assert len(big_llm.calls) == 1


# --------------------------------------------------------------------------
# Failure handling - the pinned defect
# --------------------------------------------------------------------------


async def test_episodes_from_a_failed_batch_are_not_marked_consolidated():
    """Regression: the flag-everything loop marked ALL episodes done, even those
    whose LLM batch failed - silent knowledge loss on cold storage."""
    llm = _ScriptedExtractor([RuntimeError("LLM down"), _facts("fact from batch two")])
    repo = FakeMemoryRepository()
    failed_episode = _episode("transcript that never got distilled")
    ok_episode = _episode("transcript that compressed fine")

    result = await CompressionUseCase(llm, repo).run(
        [failed_episode, ok_episode], batch_size=1  # type: ignore[arg-type]
    )

    assert failed_episode.consolidated is False, (
        "an episode whose compression failed must not be marked consolidated - "
        "the adapter would cold-store it and its knowledge is lost"
    )
    assert ok_episode.consolidated is True
    assert result.raw_transcripts_stored == 1  # only the episode that actually distilled
    assert result.semantic_fragments_created == 1


async def test_a_failed_batch_does_not_stop_later_batches():
    llm = _ScriptedExtractor([RuntimeError("LLM down"), _facts("recovered")])
    repo = FakeMemoryRepository()
    episodes = [_episode("e1"), _episode("e2"), _episode("e3")]

    result = await CompressionUseCase(llm, repo).run(
        [episodes[0], episodes[1], episodes[2]], batch_size=1  # type: ignore[arg-type]
    )

    assert len(llm.calls) == 3  # the failure did not abort the remaining batches
    assert result.semantic_fragments_created == 1


async def test_a_valid_but_empty_fact_list_still_flags_consolidated():
    """The LLM saying 'nothing worth keeping' is a legitimate result, not a failure."""
    llm = _ScriptedExtractor([{"facts": []}])
    repo = FakeMemoryRepository()
    episode = _episode("pure trivia transcript")

    result = await CompressionUseCase(llm, repo).run([episode])  # type: ignore[arg-type]

    assert episode.consolidated is True
    assert result.semantic_fragments_created == 0
    assert result.raw_transcripts_stored == 1


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------


async def test_run_with_no_episodes_makes_no_llm_calls():
    llm = _ScriptedExtractor([])
    repo = FakeMemoryRepository()

    result = await CompressionUseCase(llm, repo).run([])  # type: ignore[arg-type]

    assert (result.episodes_processed, result.semantic_fragments_created, result.raw_transcripts_stored) == (
        0,
        0,
        0,
    )
    assert llm.calls == []
    assert repo.memories == {}
