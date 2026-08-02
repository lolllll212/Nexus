"""
Tests for the Qdrant memory adapter's payload round-tripping.

These exercise the pure mapping helpers without requiring a live Qdrant
instance (the constructor touches qdrant_client, so we build the object via
__new__ to test only the payload logic).
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.domain.entities.memory import Memory, MemoryType, EmotionalWeight
from nexus.infrastructure.adapters.persistence.qdrant_memory_repository import QdrantMemoryRepository


def _repo() -> QdrantMemoryRepository:
    return QdrantMemoryRepository.__new__(QdrantMemoryRepository)


def test_payload_roundtrip_preserves_id():
    """Regression: _from_payload used to drop the memory id, breaking delete/get_by_id."""
    repo = _repo()
    m = Memory(id="memory-123", content="hello", memory_type=MemoryType.EPISODIC)
    restored = repo._from_payload(repo._to_payload(m))
    assert restored.id == "memory-123"
    assert restored.content == "hello"
    assert restored.memory_type == MemoryType.EPISODIC


def test_from_payload_prefers_point_id():
    """When reading from Qdrant, the point id (source of truth) must win."""
    repo = _repo()
    payload = repo._to_payload(Memory(id="payload-id", content="x", memory_type=MemoryType.SEMANTIC))
    restored = repo._from_payload(payload, point_id="point-id")
    assert restored.id == "point-id"


def test_payload_roundtrip_preserves_timestamps_and_counters():
    import datetime

    repo = _repo()
    m = Memory(content="c", memory_type=MemoryType.PROCEDURAL, access_count=4, consolidated=True)
    m.last_accessed_at = datetime.datetime(2026, 1, 1, 12, 0, 0)
    restored = repo._from_payload(repo._to_payload(m))
    assert restored.access_count == 4
    assert restored.consolidated is True
    assert restored.last_accessed_at == datetime.datetime(2026, 1, 1, 12, 0, 0)


def test_payload_exposes_emotional_intensity_for_filtering():
    """P1/P2: payload carries a numeric intensity for high-arousal filters."""
    repo = _repo()
    charged = Memory(
        content="scary moment",
        memory_type=MemoryType.EMOTIONAL,
        emotional_weight=EmotionalWeight(valence=-0.8, arousal=0.9),
    )
    payload = repo._to_payload(charged)
    assert abs(payload["emotional_intensity"] - 0.85) < 1e-9

    calm = Memory(content="quiet", memory_type=MemoryType.SEMANTIC)
    assert repo._to_payload(calm)["emotional_intensity"] == 0.0
