"""Domain concept entity - nodes and synapses of the neuroplastic graph memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from nexus.domain.value_objects.synapse import ConnectionType


@dataclass
class Concept:
    """
    A node in the synaptic knowledge graph.
    Strength is the neuroplastic weight - strengthens with use, decays when ignored.
    """

    label: str
    concept_type: str  # entity, topic, skill, emotion, project, person...
    id: str = field(default_factory=lambda: str(uuid4()))
    properties: Dict[str, object] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed_at: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    strength: float = 1.0

    def strengthen(self, amount: float = 0.1, max_strength: float = 10.0) -> None:
        """Hebbian rule: neurons that fire together, wire together."""
        self.strength = min(max_strength, self.strength + amount)
        self.access_count += 1
        self.last_accessed_at = datetime.utcnow()

    def decay(self, rate: float = 0.001, min_strength: float = 0.01) -> bool:
        """Apply synaptic decay. Returns True if the concept should be pruned."""
        self.strength *= 1.0 - rate
        return self.strength < min_strength


@dataclass
class SynapticConnection:
    """
    A weighted edge between two concepts.
    This IS the synapse - the physical embodiment of neuroplasticity.
    """

    source_id: str
    target_id: str
    connection_type: ConnectionType
    id: str = field(default_factory=lambda: str(uuid4()))
    weight: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_reinforced_at: datetime = field(default_factory=datetime.utcnow)
    reinforcement_count: int = 0

    def reinforce(self, amount: float = 0.1, max_weight: float = 10.0) -> None:
        self.weight = min(max_weight, self.weight + amount)
        self.reinforcement_count += 1
        self.last_reinforced_at = datetime.utcnow()

    def decay(self, rate: float = 0.001, min_weight: float = 0.01) -> bool:
        """Apply synaptic decay. Returns True if the synapse should be pruned."""
        self.weight *= 1.0 - rate
        return self.weight < min_weight
