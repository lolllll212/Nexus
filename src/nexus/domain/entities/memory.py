"""Domain memory entity - the fundamental unit of what NEXUS remembers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class MemoryType(Enum):
    """Taxonomy of memory, mirroring human memory systems."""

    EPISODIC = "episodic"  # Raw experiences: exact conversations, events
    SEMANTIC = "semantic"  # Compressed facts, rules, extracted knowledge
    PROCEDURAL = "procedural"  # Skills, learned tool usage, capabilities
    EMOTIONAL = "emotional"  # Weighted emotional associations

    @property
    def is_consolidatable(self) -> bool:
        """Episodic memories can be compressed into semantic during dreaming."""
        return self == MemoryType.EPISODIC


@dataclass(frozen=True)
class EmotionalWeight:
    """Immutable emotional valence attached to a memory."""

    valence: float  # -1.0 (negative) to 1.0 (positive)
    arousal: float  # 0.0 (calm) to 1.0 (intense)
    context: str = ""

    def __post_init__(self) -> None:
        if not -1.0 <= self.valence <= 1.0:
            raise ValueError(f"valence must be in [-1,1], got {self.valence}")
        if not 0.0 <= self.arousal <= 1.0:
            raise ValueError(f"arousal must be in [0,1], got {self.arousal}")

    @property
    def intensity(self) -> float:
        """Overall emotional magnitude, drives consolidation priority."""
        return (abs(self.valence) + self.arousal) / 2.0


@dataclass
class Memory:
    """
    A piece of the brain's memory.
    This is a pure domain entity - it knows nothing about databases or frameworks.
    """

    content: str
    memory_type: MemoryType
    id: str = field(default_factory=lambda: str(uuid4()))
    concepts: List[str] = field(default_factory=list)  # Concept IDs
    embedding: Optional[List[float]] = None
    metadata: Dict[str, object] = field(default_factory=dict)
    emotional_weight: Optional[EmotionalWeight] = None
    context_state: Dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed_at: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    consolidated: bool = False  # True when compressed by dreaming

    def accessed(self) -> None:
        """Record that this memory was recalled. Drives decay/pruning."""
        self.access_count += 1
        self.last_accessed_at = datetime.utcnow()

    def consolidate(self, new_content: str) -> Memory:
        """
        Produce a new semantic memory from this one (dreaming phase 1).
        Original is kept, flagged as consolidated, moved to cold storage.
        """
        return Memory(
            content=new_content,
            memory_type=MemoryType.SEMANTIC,
            concepts=list(self.concepts),
            metadata={"consolidated_from": self.id, **self.metadata},
            emotional_weight=self.emotional_weight,
        )

    def is_stale(self, threshold_days: int, min_accesses: int = 1) -> bool:
        """Whether this memory should be pruned (dreaming phase 2)."""
        age_days = (datetime.utcnow() - self.last_accessed_at).days
        return age_days > threshold_days and self.access_count < min_accesses
