"""Immutable emotional state value object."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class EmotionalState:
    """The emotional/contextual state of a conversation."""

    valence: float = 0.0    # -1.0 (negative) to 1.0 (positive)
    arousal: float = 0.0    # 0.0 (calm) to 1.0 (agitated)
    dominant_emotion: str = "neutral"
    mood_weights: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not -1.0 <= self.valence <= 1.0:
            raise ValueError(f"valence must be in [-1,1], got {self.valence}")
        if not 0.0 <= self.arousal <= 1.0:
            raise ValueError(f"arousal must be in [0,1], got {self.arousal}")

    @property
    def intensity(self) -> float:
        """Overall emotional magnitude, drives memory encoding strength."""
        return (abs(self.valence) + self.arousal) / 2.0
