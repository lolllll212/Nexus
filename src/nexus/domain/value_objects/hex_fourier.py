"""
Hexagonal Fourier routing - spatial frequency analysis along three axes.

A flat hex grid has three natural lattice axes 120 degrees apart. Signals on
the grid can be decomposed along each axis independently (three 1-D transforms
instead of one 2-D Cartesian transform), which is faster and matches how the
brain's grid cells encode spatial frequency.

Pure domain math - no I/O.
"""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from nexus.domain.value_objects.hex_grid import HexCoord

# The three axial basis vectors, 120 degrees apart.
# In axial (q, r): the three lattice axes are (1,0), (0,1), (1,-1).
HEX_AXES: Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]] = (
    (1, 0),
    (0, 1),
    (1, -1),
)
AXIS_NAMES: Tuple[str, str, str] = ("q", "r", "s")


def _project(coord: HexCoord, axis: Tuple[int, int]) -> int:
    """Project a hex onto an axis line, giving its scalar position along it."""
    aq, ar = axis
    return coord.q * aq + coord.r * ar


@dataclass
class AxisSpectrum:
    """The frequency content of a signal along a single hex axis."""

    axis: str
    magnitudes: List[float] = field(default_factory=list)
    dominant_frequency: int = 0

    @property
    def total_energy(self) -> float:
        # Exclude the DC (frequency 0) component: routing cares about where
        # the signal *varies* along the axis, not its overall level.
        return sum(m for i, m in enumerate(self.magnitudes) if i > 0) or 0.0


@dataclass
class HexSpectrum:
    """Full decomposition of a hex-grid signal across the three axes."""

    axes: Dict[str, AxisSpectrum] = field(default_factory=dict)

    @property
    def dominant_axis(self) -> str:
        """The axis carrying the most spatial-frequency energy."""
        best = max(self.axes.values(), key=lambda a: a.total_energy)
        return best.axis


def hex_fourier_transform(signal: Dict[HexCoord, float]) -> HexSpectrum:
    """
    Decompose a signal on the hex grid along the three 120-degree axes.

    Each axis is treated as a 1-D line: cells are projected onto the axis,
    their values binned by projection coordinate, and a discrete transform
    extracts per-frequency magnitude. Returns a HexSpectrum.
    """
    spectrum = HexSpectrum()
    for name, axis in zip(AXIS_NAMES, HEX_AXES):
        bins: Dict[int, float] = {}
        for coord, value in signal.items():
            position = _project(coord, axis)
            bins[position] = bins.get(position, 0.0) + value
        magnitudes = _transform_1d(bins)
        dominant = _dominant_frequency(magnitudes)
        spectrum.axes[name] = AxisSpectrum(
            axis=name,
            magnitudes=magnitudes,
            dominant_frequency=dominant,
        )
    return spectrum


def _transform_1d(bins: Dict[int, float]) -> List[float]:
    """Compute frequency magnitudes along a 1-D signal (bins keyed by position)."""
    if not bins:
        return []
    positions = sorted(bins.keys())
    samples = [bins[p] for p in positions]
    n = len(samples)
    magnitudes: List[float] = []
    for freq in range(n):
        total = complex(0.0, 0.0)
        for k, sample in enumerate(samples):
            angle = -2.0 * math.pi * freq * k / n
            total += sample * cmath.exp(complex(0.0, angle))
        magnitudes.append(abs(total) / n)
    return magnitudes


def _dominant_frequency(magnitudes: List[float]) -> int:
    """The frequency bin (>=1) with the most energy; 0 if all flat."""
    if len(magnitudes) < 2:
        return 0
    best_freq = 0
    best_energy = 0.0
    for freq, magnitude in enumerate(magnitudes):
        if freq == 0:
            continue  # DC component carries no spatial-frequency structure
        if magnitude > best_energy:
            best_energy = magnitude
            best_freq = freq
    return best_freq
