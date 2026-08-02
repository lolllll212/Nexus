"""
Hierarchical hexagonal tiling - fractal H3-style indexing.

Each hexagon at resolution `r` contains exactly 7 children at resolution
`r+1` (aperture 7). This lets the brain zoom seamlessly from macro-level
concepts (low resolution) down to micro-level details (high resolution) and
back, using integer axial coordinates scaled by 3 per resolution step.

Pure domain math - no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional

from nexus.domain.value_objects.hex_grid import HexCoord

# The 7 child offsets (center + ring-at-radius-2 corners) for aperture 7.
_CHILD_OFFSETS: List[HexCoord] = [
    HexCoord(0, 0),
    HexCoord(2, 0),
    HexCoord(1, 1),
    HexCoord(-1, 2),
    HexCoord(-2, 1),
    HexCoord(-1, -1),
    HexCoord(1, -2),
]

_SCALE = 3  # child axial coordinates are 3x the parent's


@dataclass(frozen=True)
class HexIndex:
    """A hexagon at a given resolution in the fractal tiling."""

    q: int
    r: int
    resolution: int = 0

    def coord(self) -> HexCoord:
        return HexCoord(self.q, self.r)

    @property
    def is_root(self) -> bool:
        return self.resolution == 0

    def parent(self) -> Optional["HexIndex"]:
        """The containing hexagon at resolution-1, or None at the root."""
        if self.is_root:
            return None
        for offset in _CHILD_OFFSETS:
            dq, dr = offset.q, offset.r
            if (self.q - dq) % _SCALE == 0 and (self.r - dr) % _SCALE == 0:
                return HexIndex(
                    (self.q - dq) // _SCALE,
                    (self.r - dr) // _SCALE,
                    self.resolution - 1,
                )
        return None

    def children(self) -> List["HexIndex"]:
        """The 7 hexagons at resolution+1 contained by this one."""
        return [
            HexIndex(self.q * _SCALE + o.q, self.r * _SCALE + o.r, self.resolution + 1)
            for o in _CHILD_OFFSETS
        ]

    def ancestors(self) -> Iterator["HexIndex"]:
        """Walk up the hierarchy to the root."""
        current: Optional[HexIndex] = self.parent()
        while current is not None:
            yield current
            current = current.parent()

    def contains(self, other: "HexIndex") -> bool:
        """True if `other` (at any higher resolution) lives inside this cell."""
        if other.resolution < self.resolution:
            return False
        current: Optional[HexIndex] = other
        while current is not None and current.resolution > self.resolution:
            current = current.parent()
        return current == self

    def zoom_in(self, levels: int = 1) -> "HexIndex":
        """Descend into the center child `levels` times (macro -> micro)."""
        result = self
        for _ in range(levels):
            result = result.children()[0]
        return result

    def zoom_out(self, levels: int = 1) -> "HexIndex":
        """Ascend to the parent `levels` times (micro -> macro)."""
        result = self
        for _ in range(levels):
            if result.is_root:
                break
            parent = result.parent()
            if parent is None:
                break
            result = parent
        return result

    @property
    def relative_area(self) -> int:
        """Area relative to a resolution-0 cell (7 children each step)."""
        return 7 ** self.resolution


def hex_index_at(coord: HexCoord, resolution: int = 0) -> HexIndex:
    """Wrap a raw hex coordinate as an index at a given resolution."""
    return HexIndex(q=coord.q, r=coord.r, resolution=resolution)
