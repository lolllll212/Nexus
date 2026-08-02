"""Cortical column entity - a weighted hexagonal processing unit.

Each column is one hexagon of the cortex. The thalamus re-weights columns
based on task urgency; the basal ganglia bids them against each other to
select the next action; the amygdala tags them with survival/utility valence.

Dependency Rule: pure domain entity - no I/O, no frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

from nexus.domain.value_objects.hex_grid import HexCoord
from nexus.domain.value_objects.valence import ValenceTag


@dataclass
class CorticalColumn:
    """One hexagonal cortical column with a dynamic gate weight."""

    name: str
    hex_coord: HexCoord = field(default_factory=lambda: HexCoord(0, 0))
    id: str = field(default_factory=lambda: str(uuid4()))
    base_weight: float = 1.0       # resting strength (0..1)
    gate_weight: float = 1.0       # current attention gate (0..1)
    urgency_sensitivity: float = 1.0  # how strongly the thalamus moves it
    valence: Optional[ValenceTag] = None
    metadata: dict = field(default_factory=dict)

    @property
    def effective_weight(self) -> float:
        """The gated weight the basal ganglia uses for bidding."""
        return self.base_weight * self.gate_weight

    def gate(self, urgency: float) -> float:
        """
        Thalamic reweighting. Urgency in [0,1] pushes the gate open; calm
        tasks let it relax back toward the base weight.
        """
        delta = (urgency - 0.5) * self.urgency_sensitivity
        self.gate_weight = max(0.0, min(1.5, self.gate_weight + delta))
        return self.gate_weight

    def bid(self, urgency: float) -> float:
        """Competitive bid for the basal ganglia: gated weight boosted by urgency."""
        return self.effective_weight * (0.5 + urgency * self.urgency_sensitivity)
