"""
GridCellNavigationUseCase - conceptual pathfinding on a hexagonal grid.

Concepts are placed on hex cells (stable hash-based positions), obstacles mark
inaccessible or weakly-connected concepts, and A* finds the shortest semantic
route between two concepts - the brain's inherent sense of conceptual space.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional

from nexus.domain.value_objects.hex_grid import HexCoord, HexGrid, hex_line


@dataclass
class NavigationResult:
    path: List[HexCoord] = field(default_factory=list)
    distance: int = 0
    found: bool = False


def concept_coord(label: str, radius: int = 30) -> HexCoord:
    """Stable deterministic hex coordinate inside the grid, derived from a concept label."""
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    i = 0
    while True:
        h = hashlib.sha256(digest + i.to_bytes(4, "big")).digest()
        q = int.from_bytes(h[:4], "big") % (2 * radius + 1) - radius
        r = int.from_bytes(h[4:8], "big") % (2 * radius + 1) - radius
        coord = HexCoord(q, r)
        if coord.distance_to(HexCoord(0, 0)) <= radius:
            return coord
        i += 1


class GridCellNavigationUseCase:
    """Maps concepts onto a hex grid and navigates between them."""

    def __init__(self, radius: int = 30) -> None:
        self._grid = HexGrid(radius=radius)
        self._placements: dict[str, HexCoord] = {}

    def place_concept(self, label: str, coord: Optional[HexCoord] = None) -> HexCoord:
        coord = coord or concept_coord(label, self._grid.radius)
        if self._grid.contains(coord):
            self._grid.set_feature(coord, label)
            self._placements[label] = coord
        return coord

    def block_region(self, labels: List[str]) -> None:
        for label in labels:
            coord = self._placements.get(label)
            if coord:
                self._grid.block(coord)

    def locate(self, label: str) -> Optional[HexCoord]:
        return self._placements.get(label)

    def straight_line(self, start: HexCoord, goal: HexCoord) -> List[HexCoord]:
        return hex_line(start, goal)

    def navigate(self, start_label: str, goal_label: str) -> NavigationResult:
        start = self._placements.get(start_label)
        goal = self._placements.get(goal_label)
        if start is None or goal is None:
            return NavigationResult()
        path = self._grid.pathfind(start, goal)
        if path is None:
            return NavigationResult(distance=start.distance_to(goal), found=False)
        return NavigationResult(path=path, distance=len(path) - 1, found=True)

    def distance_between(self, label_a: str, label_b: str) -> Optional[int]:
        a, b = self._placements.get(label_a), self._placements.get(label_b)
        if a is None or b is None:
            return None
        return a.distance_to(b)
