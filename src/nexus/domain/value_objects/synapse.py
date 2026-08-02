"""Immutable synapse value object - types of connections between concepts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectionType(Enum):
    """Taxonomy of how two concepts are linked in the graph."""
    SEMANTIC = "semantic"    # Share meaning (e.g., "React" - "component")
    TEMPORAL = "temporal"    # Occurred close in time
    CAUSAL = "causal"        # One causes/influences the other
    EMOTIONAL = "emotional"  # Associated through emotional weight
    CONTEXTUAL = "contextual"  # Co-occur in the same context


@dataclass(frozen=True)
class SynapseConfig:
    """Tunable neuroplasticity parameters (dreaming-phase overrides)."""

    initial_weight: float = 1.0
    hebbian_learning_rate: float = 0.1
    decay_rate: float = 0.001
    min_weight: float = 0.01
    max_weight: float = 10.0
    strengthening_threshold: int = 3
