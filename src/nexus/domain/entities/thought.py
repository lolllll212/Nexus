"""Domain thought entity - a unit of reasoning in the conscious loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4


class ThoughtType(Enum):
    """Kinds of thoughts the brain produces."""

    OBSERVATION = "observation"  # "I see that..."
    REASONING = "reasoning"  # "Therefore..."
    HYPOTHESIS = "hypothesis"  # "What if..."
    ACTION = "action"  # "I will call tool X"
    INSIGHT = "insight"  # A subconscious realization
    ANSWER = "answer"  # Final response to user
    DREAM = "dream"  # Produced during dreaming cycles


@dataclass
class Thought:
    """A single unit of cognitive processing."""

    content: str
    thought_type: ThoughtType
    id: str = field(default_factory=lambda: str(uuid4()))
    parent_id: Optional[str] = None  # Chain of thought
    concepts: List[str] = field(default_factory=list)
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")
