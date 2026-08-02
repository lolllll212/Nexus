"""Tests for the synaptic graph domain entities - the neuroplastic core."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.domain.entities.concept import Concept, SynapticConnection
from nexus.domain.entities.memory import Memory, MemoryType, EmotionalWeight
from nexus.domain.value_objects.synapse import ConnectionType
from nexus.domain.value_objects.emotion import EmotionalState


class TestConceptNeuroplasticity:
    def test_strengthen_hitmax(self):
        c = Concept(label="react", concept_type="tech")
        c.strengthen(5.0)
        assert c.strength == 6.0
        assert c.access_count == 1

    def test_decay_prunes_below_floor(self):
        c = Concept(label="old", concept_type="topic")
        assert c.decay(rate=0.5, min_strength=0.6) is True  # 1.0 -> 0.5 < 0.6
        assert c.decay(rate=0.1, min_strength=0.01) is False

    def test_strengthen_capped_at_max(self):
        c = Concept(label="x", concept_type="topic")
        c.strengthen(9.9)
        assert c.strength == 10.0  # capped


class TestSynapticConnection:
    def test_reinforce_increases_weight(self):
        conn = SynapticConnection(source_id="a", target_id="b", connection_type=ConnectionType.CAUSAL)
        conn.reinforce(0.5)
        assert conn.weight == 1.5
        assert conn.reinforcement_count == 1

    def test_decay_returns_prune_signal(self):
        conn = SynapticConnection(source_id="a", target_id="b", connection_type=ConnectionType.SEMANTIC)
        assert conn.decay(rate=0.9, min_weight=0.2) is True


class TestMemoryConsolidation:
    def test_consolidate_produces_semantic(self):
        ep = Memory(content="raw transcript", memory_type=MemoryType.EPISODIC)
        sem = ep.consolidate("distilled fact")
        assert sem.memory_type == MemoryType.SEMANTIC
        assert sem.metadata["consolidated_from"] == ep.id
        assert not ep.consolidated  # original untouched until flagged

    def test_stale_detection(self):
        import datetime

        m = Memory(content="x", memory_type=MemoryType.EPISODIC)
        m.last_accessed_at = datetime.datetime.utcnow() - datetime.timedelta(days=200)
        assert m.is_stale(threshold_days=90)

    def test_emotional_weight_validation(self):
        with pytest.raises(ValueError):
            EmotionalWeight(valence=2.0, arousal=0.5)
        with pytest.raises(ValueError):
            EmotionalWeight(valence=0.5, arousal=-1.0)

    def test_emotional_state_intensity(self):
        s = EmotionalState(valence=1.0, arousal=1.0)
        assert s.intensity == 1.0
