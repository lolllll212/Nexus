"""Immutable emotional state value object."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

_NEGATIVE_WORDS = {
    "angry",
    "anxious",
    "awful",
    "bad",
    "broken",
    "confused",
    "disappointed",
    "frustrated",
    "hate",
    "hurt",
    "issue",
    "lost",
    "panic",
    "sad",
    "scared",
    "sorry",
    "stress",
    "stuck",
    "terrible",
    "upset",
    "wrong",
}
_POSITIVE_WORDS = {
    "amazing",
    "awesome",
    "excellent",
    "glad",
    "good",
    "great",
    "happy",
    "helpful",
    "love",
    "nice",
    "perfect",
    "pleased",
    "thanks",
    "thank",
    "wonderful",
}
_HIGH_AROUSAL_WORDS = {
    "asap",
    "crash",
    "critical",
    "emergency",
    "now",
    "panic",
    "urgent",
    "worried",
}


@dataclass(frozen=True)
class EmotionalState:
    """The emotional/contextual state of a conversation."""

    valence: float = 0.0  # -1.0 (negative) to 1.0 (positive)
    arousal: float = 0.0  # 0.0 (calm) to 1.0 (agitated)
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

    def blend(self, other: "EmotionalState", alpha: float = 0.3) -> "EmotionalState":
        """Combine this state with an incoming one (the room's running emotional weight)."""
        valence = round(self.valence * (1.0 - alpha) + other.valence * alpha, 3)
        arousal = round(self.arousal * (1.0 - alpha) + other.arousal * alpha, 3)
        weights = dict(self.mood_weights)
        for key, value in other.mood_weights.items():
            weights[key] = weights.get(key, 0.0) + value
        return EmotionalState(
            valence=valence,
            arousal=arousal,
            dominant_emotion=(
                other.dominant_emotion if other.dominant_emotion != "neutral" else self.dominant_emotion
            ),
            mood_weights=weights,
        )

    def tone_directive(self) -> str:
        """System-prompt fragment that makes the cortex modulate tone from the room's mood."""
        parts: list[str] = []
        if self.valence < -0.3:
            parts.append("the user seems distressed - be warm, patient, and reassuring")
        elif self.valence > 0.3:
            parts.append("the user seems positive - match their energy with warmth")
        if self.arousal > 0.6:
            parts.append("the user is agitated - stay calm, concise, and de-escalating")
        if not parts:
            return ""
        return "Tone directive: " + "; ".join(parts) + "."


def infer_emotional_state(text: str) -> EmotionalState:
    """Lexicon-based emotional inference from raw message text (pure, testable)."""
    tokens = [t.strip(".,!?()'\"").lower() for t in text.split()]
    if not tokens:
        return EmotionalState()

    negative = sum(1 for t in tokens if t in _NEGATIVE_WORDS)
    positive = sum(1 for t in tokens if t in _POSITIVE_WORDS)
    arousal_hits = sum(1 for t in tokens if t in _HIGH_AROUSAL_WORDS)

    valence = max(-1.0, min(1.0, (positive - negative) / max(1, len(tokens)) * 2.0))
    arousal = max(0.0, min(1.0, arousal_hits / max(1, len(tokens)) * 3.0))

    dominant = "positive" if positive > negative else ("negative" if negative > positive else "neutral")

    return EmotionalState(
        valence=valence,
        arousal=arousal,
        dominant_emotion=dominant,
        mood_weights={
            "negative": float(negative),
            "positive": float(positive),
            "arousal": float(arousal_hits),
        },
    )
