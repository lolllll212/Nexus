"""
BoundlessScalingUseCase - fractal zoom through hexagonal tiling.

Uses the H3-style aperture-7 hierarchy to zoom seamlessly from macro-level
concepts (resolution 0) down to micro-level details (high resolution). A
concept's HexIndex can be zoomed in to enumerate its sub-aspects or zoomed
out to find its containing super-concept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from nexus.domain.value_objects.hex_index import HexIndex


@dataclass
class ZoomResult:
    index: HexIndex
    resolution: int
    children: List[HexIndex] = field(default_factory=list)
    area: int = 1


class BoundlessScalingUseCase:
    """Zoom macro <-> micro over the hexagonal hierarchy."""

    def zoom_in(self, index: HexIndex, levels: int = 1) -> ZoomResult:
        """Descend into finer detail (macro -> micro)."""
        result = index.zoom_in(levels)
        return ZoomResult(
            index=result, resolution=result.resolution, children=result.children(), area=result.relative_area
        )

    def zoom_out(self, index: HexIndex, levels: int = 1) -> ZoomResult:
        """Ascend to coarser scope (micro -> macro)."""
        result = index.zoom_out(levels)
        return ZoomResult(
            index=result, resolution=result.resolution, children=result.children(), area=result.relative_area
        )

    def contains(self, macro: HexIndex, micro: HexIndex) -> bool:
        """True when `micro` lives inside `macro` (at any resolution below it)."""
        return macro.contains(micro)

    def ancestors(self, index: HexIndex) -> List[HexIndex]:
        return list(index.ancestors())
