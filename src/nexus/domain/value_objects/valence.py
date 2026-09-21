"""Amygdala-inspired valence tag - survival/utility scoring of data patterns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValenceTag:
    """Priority scoring attached to a pattern/memory by the amygdala.

    `survival` scores how critical the pattern is to keeping the system alive
    (failing infra, security threats, breaking changes). `utility` scores how
    broadly useful it is (reusable solutions, high-frequency patterns).
    """

    survival: float  # 0.0 (irrelevant) to 1.0 (life-or-death)
    utility: float  # 0.0 (niche) to 1.0 (universally useful)
    label: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.survival <= 1.0:
            raise ValueError(f"survival must be in [0,1], got {self.survival}")
        if not 0.0 <= self.utility <= 1.0:
            raise ValueError(f"utility must be in [0,1], got {self.utility}")

    @property
    def priority(self) -> float:
        """Combined urgency: survival dominates, utility adds."""
        return max(self.survival, 0.5 * self.utility)
