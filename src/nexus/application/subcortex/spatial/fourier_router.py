"""
FourierRouterUseCase - spatial-frequency routing along hex axes.

Signals (concept activations, memory density) are laid out on a hex grid and
decomposed along the three 120-degree lattice axes. The axis carrying the most
spatial-frequency energy is the dominant "direction of change" - used to route
attention or dispatch work along that dimension.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from nexus.domain.value_objects.hex_fourier import HexSpectrum, hex_fourier_transform
from nexus.domain.value_objects.hex_grid import HexCoord


@dataclass
class RoutingResult:
    dominant_axis: str
    spectrum: HexSpectrum
    axis_energy: Dict[str, float]


class FourierRouterUseCase:
    """Routes signals by the direction of their spatial-frequency energy."""

    def route(self, signal: Dict[HexCoord, float]) -> RoutingResult:
        spectrum = hex_fourier_transform(signal)
        axis_energy = {name: axis.total_energy for name, axis in spectrum.axes.items()}
        return RoutingResult(dominant_axis=spectrum.dominant_axis, spectrum=spectrum, axis_energy=axis_energy)

    def dominant_frequencies(self, signal: Dict[HexCoord, float]) -> Dict[str, int]:
        spectrum = hex_fourier_transform(signal)
        return {name: axis.dominant_frequency for name, axis in spectrum.axes.items()}

    def route_labels(self, placements: Dict[str, HexCoord], weights: Dict[str, float]) -> RoutingResult:
        """Build a signal from labelled hex placements and route it."""
        signal = {coord: weights.get(label, 1.0) for label, coord in placements.items()}
        return self.route(signal)
