"""
Hexagonal coordinate system - axial/cube math for grid-cell navigation.

Axial coordinates (q, r) describe a point on a flat-top hex grid. The third
cube axis s = -q - r is implicit. This gives the brain an inherent sense of
conceptual space: concepts can be placed on hexagons, distances measured,
paths planned.

Dependency Rule: pure domain value objects - no I/O, no frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Set, Tuple

# The six neighbor directions in axial coordinates.
HEX_DIRECTIONS: Tuple[Tuple[int, int], ...] = (
    (1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1),
)


@dataclass(frozen=True, order=True)
class HexCoord:
    """An axial hexagonal coordinate (q, r). The third axis s = -q-r."""

    q: int
    r: int

    @property
    def s(self) -> int:
        return -self.q - self.r

    def cube(self) -> Tuple[int, int, int]:
        return (self.q, self.r, self.s)

    def distance_to(self, other: "HexCoord") -> int:
        return (abs(self.q - other.q) + abs(self.r - other.r) + abs(self.s - other.s)) // 2

    def neighbor(self, direction: int) -> "HexCoord":
        dq, dr = HEX_DIRECTIONS[direction % 6]
        return HexCoord(self.q + dq, self.r + dr)

    def neighbors(self) -> Iterator["HexCoord"]:
        for direction in range(6):
            yield self.neighbor(direction)

    def ring(self, radius: int) -> List["HexCoord"]:
        """The cells forming a ring around this cell at the given radius."""
        if radius <= 0:
            return [self]
        # Start at the corner in direction 4, then walk the ring steps in
        # cyclic order so every visited cell stays exactly `radius` away.
        start = HexCoord(self.q - radius, self.r + radius)
        ring: List[HexCoord] = []
        for i in range(6):
            for _ in range(radius):
                ring.append(start)
                start = start.neighbor(i)
        return ring

    def move_toward(self, other: "HexCoord", amount: int = 1) -> "HexCoord":
        """Step `amount` hexes toward `other` along the shortest path."""
        if self == other or amount <= 0:
            return self
        target = self
        for _ in range(amount):
            if target == other:
                break
            best: Optional["HexCoord"] = None
            best_dist = target.distance_to(other)
            for neighbor in target.neighbors():
                distance = neighbor.distance_to(other)
                if distance < best_dist:
                    best_dist = distance
                    best = neighbor
            if best is None:
                break
            target = best
        return target

    def __hash__(self) -> int:
        return hash((self.q, self.r))


def _round_half_up(value: float) -> int:
    """Round .5 away from zero (avoids banker's rounding in move_toward/hex_line)."""
    if value >= 0:
        return int(value + 0.5)
    return int(value - 0.5)


def _linear_interpolate(a: HexCoord, b: HexCoord, t: float) -> HexCoord:
    a_cube = a.cube()
    b_cube = b.cube()
    lerp = (
        _round_half_up(a_cube[0] + (b_cube[0] - a_cube[0]) * t),
        _round_half_up(a_cube[1] + (b_cube[1] - a_cube[1]) * t),
        _round_half_up(a_cube[2] + (b_cube[2] - a_cube[2]) * t),
    )
    # Rounding may break the s = -q-r invariant; fix the largest delta.
    x, y, z = lerp
    dx, dy, dz = abs(x - a_cube[0]), abs(y - a_cube[1]), abs(z - a_cube[2])
    if dx > dy and dx > dz:
        x = -y - z
    elif dy > dz:
        y = -x - z
    else:
        z = -x - y
    return HexCoord(x, y)


def hex_line(a: HexCoord, b: HexCoord) -> List[HexCoord]:
    """All cells along the straight line between two hexes (Bresenham-style)."""
    dist = a.distance_to(b)
    results: List[HexCoord] = []
    for i in range(dist + 1):
        results.append(_linear_interpolate(a, b, i / max(1, dist)))
    return results


class HexGrid:
    """A bounded conceptual space made of hexagons with pathfinding."""

    def __init__(self, radius: int = 10) -> None:
        self._radius = radius
        self._blocked: Set[HexCoord] = set()
        self._features: Dict[HexCoord, str] = {}

    @property
    def radius(self) -> int:
        return self._radius

    def contains(self, coord: HexCoord) -> bool:
        return coord.distance_to(HexCoord(0, 0)) <= self._radius

    def block(self, coord: HexCoord) -> None:
        if self.contains(coord):
            self._blocked.add(coord)

    def unblock(self, coord: HexCoord) -> None:
        self._blocked.discard(coord)

    def is_blocked(self, coord: HexCoord) -> bool:
        return coord in self._blocked

    def set_feature(self, coord: HexCoord, label: str) -> None:
        if self.contains(coord):
            self._features[coord] = label

    def feature_at(self, coord: HexCoord) -> Optional[str]:
        return self._features.get(coord)

    def passable(self, coord: HexCoord) -> bool:
        return self.contains(coord) and not self.is_blocked(coord)

    def reachable_neighbors(self, coord: HexCoord) -> List[HexCoord]:
        return [n for n in coord.neighbors() if self.passable(n)]

    def pathfind(self, start: HexCoord, goal: HexCoord, max_iterations: int = 1000) -> Optional[List[HexCoord]]:
        """A* shortest path. Returns the cell sequence or None if unreachable."""
        if not self.passable(start) or not self.passable(goal):
            return None

        open_set: Set[HexCoord] = {start}
        came_from: Dict[HexCoord, HexCoord] = {}
        g_score: Dict[HexCoord, int] = {start: 0}

        def heuristic(c: HexCoord) -> int:
            return c.distance_to(goal)

        while open_set and max_iterations > 0:
            max_iterations -= 1
            current = min(open_set, key=lambda c: g_score.get(c, 10**9) + heuristic(c))
            if current == goal:
                return _reconstruct_path(came_from, current)
            open_set.remove(current)
            for neighbor in self.reachable_neighbors(current):
                tentative = g_score.get(current, 10**9) + 1
                if tentative < g_score.get(neighbor, 10**9):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative
                    open_set.add(neighbor)
        return None


def _reconstruct_path(came_from: Dict[HexCoord, HexCoord], current: HexCoord) -> List[HexCoord]:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    return list(reversed(path))
