"""Regression tests for the six hexagon-based cognition subsystems.

Covers the pure domain math (hex grids, hexagonal Fourier, H3-style tiling),
the three subcortical control loops (thalamus / basal ganglia / amygdala),
and their wiring through the event bus coordinator.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nexus.application.subcortex.amygdala import AmygdalaUseCase, tag_text
from nexus.application.subcortex.basal_ganglia import BasalGangliaUseCase
from nexus.application.subcortex.spatial.fourier_router import FourierRouterUseCase
from nexus.application.subcortex.spatial.grid_cells import (
    GridCellNavigationUseCase,
    concept_coord,
)
from nexus.application.subcortex.spatial.hex_scaling import BoundlessScalingUseCase
from nexus.application.subcortex.thalamus import ThalamicGatingUseCase, estimate_urgency
from nexus.domain.ports.event_bus import Event, EventTopic
from nexus.domain.value_objects.hex_fourier import HEX_AXES, hex_fourier_transform
from nexus.domain.value_objects.hex_grid import HexCoord, hex_line
from nexus.domain.value_objects.hex_index import HexIndex, hex_index_at
from nexus.domain.value_objects.valence import ValenceTag
from tests.fakes import (
    FakeActionPolicyStore,
    FakeCorticalColumnRegistry,
    FakeEventBus,
)


# --------------------------------------------------------------------------- #
#  Domain: hexagonal coordinates
# --------------------------------------------------------------------------- #
class TestHexCoordMath:
    def test_distance_is_symmetric(self):
        a, b = HexCoord(2, -1), HexCoord(-3, 4)
        assert a.distance_to(b) == b.distance_to(a) == 5

    def test_origin_distance(self):
        assert HexCoord(0, 0).distance_to(HexCoord(3, -1)) == 3

    def test_six_neighbors_surround_cell(self):
        center = HexCoord(0, 0)
        neighbors = set(center.neighbors())
        assert len(neighbors) == 6
        for n in neighbors:
            assert n.distance_to(center) == 1

    def test_ring_radius(self):
        ring = HexCoord(0, 0).ring(2)
        assert len(ring) == 12
        for cell in ring:
            assert cell.distance_to(HexCoord(0, 0)) == 2

    def test_hex_line_endpoints_included(self):
        line = hex_line(HexCoord(0, 0), HexCoord(4, -2))
        assert line[0] == HexCoord(0, 0)
        assert line[-1] == HexCoord(4, -2)
        for cell in line:
            assert cell.distance_to(HexCoord(0, 0)) <= HexCoord(4, -2).distance_to(HexCoord(0, 0))

    def test_move_toward_steps_single(self):
        start, goal = HexCoord(0, 0), HexCoord(5, 5)
        stepped = start.move_toward(goal, 1)
        assert stepped.distance_to(start) == 1
        assert stepped.distance_to(goal) == 9


class TestHexGridPathfinding:
    def test_pathfind_shortest_path(self):
        grid = _grid_with_corridor()
        path = grid.pathfind(HexCoord(0, 0), HexCoord(4, 0))
        assert path is not None
        assert path[0] == HexCoord(0, 0) and path[-1] == HexCoord(4, 0)
        # Blocked straight line forces the detour; path length reflects it
        assert len(path) >= 5

    def test_pathfind_returns_none_when_goal_blocked(self):
        grid = _grid_with_corridor()
        assert grid.pathfind(HexCoord(0, 0), HexCoord(3, 0)) is not None
        grid.block(HexCoord(4, 0))
        assert grid.pathfind(HexCoord(0, 0), HexCoord(4, 0)) is None


def _grid_with_corridor():
    from nexus.domain.value_objects.hex_grid import HexGrid

    grid = HexGrid(radius=10)
    for i in range(1, 4):
        grid.block(HexCoord(i, -i))
    return grid


# --------------------------------------------------------------------------- #
#  Domain: hexagonal Fourier transform
# --------------------------------------------------------------------------- #
class TestHexFourier:
    def test_axes_span_120_degrees(self):
        assert len(HEX_AXES) == 3
        assert HEX_AXES[0] == (1, 0)
        assert HEX_AXES[1] == (0, 1)
        assert HEX_AXES[2] == (1, -1)

    def test_axis_names_present(self):
        signal = {HexCoord(0, 0): 1.0, HexCoord(2, 1): 0.5}
        spectrum = hex_fourier_transform(signal)
        assert set(spectrum.axes) == {"q", "r", "s"}
        assert spectrum.dominant_axis in {"q", "r", "s"}

    def test_energy_concentrates_on_primary_axis(self):
        # Signal stretched along the q axis: q-coordinate changes, r stays 0
        signal = {HexCoord(i, 0): float(i % 2) for i in range(6)}
        spectrum = hex_fourier_transform(signal)
        assert spectrum.axes["q"].total_energy > spectrum.axes["r"].total_energy

    def test_dominant_frequency_detects_oscillation(self):
        signal = {HexCoord(i, 0): float(i % 2) for i in range(8)}
        spectrum = hex_fourier_transform(signal)
        assert spectrum.axes["q"].dominant_frequency >= 1


# --------------------------------------------------------------------------- #
#  Domain: H3-style hierarchical tiling
# --------------------------------------------------------------------------- #
class TestHexIndexHierarchy:
    def test_root_has_seven_children(self):
        root = HexIndex(0, 0, resolution=0)
        children = root.children()
        assert len(children) == 7
        assert all(c.resolution == 1 for c in children)

    def test_child_parent_roundtrip(self):
        root = HexIndex(0, 0)
        child = root.children()[3]
        assert child.parent() == root

    def test_contains_micro_within_macro(self):
        macro = HexIndex(0, 0)
        micro = macro.zoom_in(3)
        assert macro.contains(micro)
        assert micro.contains(macro) is False

    def test_zoom_out_returns_to_root(self):
        deep = HexIndex(0, 0).zoom_in(5)
        assert deep.resolution == 5
        assert deep.zoom_out(5) == HexIndex(0, 0)

    def test_relative_area_scales_by_seven(self):
        assert HexIndex(0, 0).relative_area == 1
        assert hex_index_at(HexCoord(3, -2), resolution=2).relative_area == 49


# --------------------------------------------------------------------------- #
#  Subcortex loop 1: Thalamus - attention gating
# --------------------------------------------------------------------------- #
class TestThalamicGating:
    async def test_urgency_from_lexical_cues(self):
        assert estimate_urgency("the service is DOWN, production CRASH") > 0.5
        assert estimate_urgency("routine status update") < 0.3

    async def test_gate_reweights_columns_and_publishes(self):
        bus = FakeEventBus()
        registry = FakeCorticalColumnRegistry()
        for name in ("memory", "reasoning", "planning"):
            await registry.get_or_create(name)

        use_case = ThalamicGatingUseCase(registry, bus)
        result = await use_case.gate("URGENT security incident now")

        assert result.columns_gated == 3
        assert result.urgency > 0.5
        topics = [e.topic for e in bus.published]
        assert EventTopic.ATTENTION_GATED in topics
        gating_event = next(e for e in bus.published if e.topic == EventTopic.ATTENTION_GATED)
        assert gating_event.payload["urgency"] == result.urgency

    async def test_gate_moves_weights_toward_urgency(self):
        bus = FakeEventBus()
        registry = FakeCorticalColumnRegistry()
        column = await registry.get_or_create("priority", base_weight=0.8, urgency_sensitivity=2.0)
        before = column.effective_weight
        await ThalamicGatingUseCase(registry, bus).gate("critical failure")
        updated = await registry.get(column.id)
        assert updated is not None
        assert updated.gate_weight > 1.0 or updated.gate_weight < 1.0
        assert updated.effective_weight != before


# --------------------------------------------------------------------------- #
#  Subcortex loop 2: Basal ganglia - competitive bidding + Q-learning
# --------------------------------------------------------------------------- #
class TestBasalGanglia:
    async def test_highest_bid_wins(self):
        bus = FakeEventBus()
        registry = FakeCorticalColumnRegistry()
        await registry.get_or_create("weak", base_weight=0.2)
        strong = await registry.get_or_create("strong", base_weight=0.9)
        policy = FakeActionPolicyStore()

        use_case = BasalGangliaUseCase(registry, policy, bus)
        use_case.EXPLORATION_RATE = 0.0  # deterministic greedy selection for the test
        result = await use_case.select(
            "solve",
            {"weak": "weak-action", "strong": "strong-action"},
            urgency=0.0,
        )
        assert result.selected.column == strong.name
        assert result.selected.action_id == "strong-action"
        assert result.all_bids["strong"] > result.all_bids["weak"]

    async def test_reward_updates_q_table(self):
        bus = FakeEventBus()
        registry = FakeCorticalColumnRegistry()
        await registry.get_or_create("col", base_weight=0.5)
        policy = FakeActionPolicyStore()
        use_case = BasalGangliaUseCase(registry, policy, bus)

        await use_case.select("stateA", {"col": "actionX"})
        assert await policy.get_value("stateA", "actionX") == 0.0

        await use_case.apply_reward("stateA", "actionX", 1.0)
        q = await policy.get_value("stateA", "actionX")
        assert q > 0.0
        assert q < 1.0  # alpha=0.2 moves only partway

    async def test_reward_from_event(self):
        bus = FakeEventBus()
        registry = FakeCorticalColumnRegistry()
        policy = FakeActionPolicyStore()
        use_case = BasalGangliaUseCase(registry, policy, bus)

        await use_case.update_from_event(
            Event(
                topic=EventTopic.TOOL_USED,
                payload={"state": "stateB", "action": "toolY", "success": 1.0},
            )
        )
        assert await policy.get_value("stateB", "toolY") > 0.0

    async def test_publishes_action_selected(self):
        bus = FakeEventBus()
        registry = FakeCorticalColumnRegistry()
        await registry.get_or_create("col", base_weight=0.5)
        use_case = BasalGangliaUseCase(registry, FakeActionPolicyStore(), bus)
        await use_case.select("stateC", {"col": "act"})
        assert any(e.topic == EventTopic.ACTION_SELECTED for e in bus.published)


# --------------------------------------------------------------------------- #
#  Subcortex loop 3: Amygdala - valence tagging
# --------------------------------------------------------------------------- #
class TestAmygdalaValence:
    async def test_survival_tokens_raise_priority(self):
        tag = tag_text("production crash, data loss, security breach")
        assert tag.survival > 0.5
        assert tag.utility == 0.0

    async def test_utility_tokens_raise_utility(self):
        tag = tag_text("reusable pattern with a common solution and api template")
        assert tag.utility > 0.3

    async def test_tag_validates_ranges(self):
        with pytest.raises(ValueError):
            ValenceTag(survival=1.5, utility=0.0)

    async def test_tag_publishes_event_with_priority(self):
        bus = FakeEventBus()
        use_case = AmygdalaUseCase(bus)
        result = await use_case.tag("CRITICAL outage in production")
        assert result.urgent is True
        tagged = [e for e in bus.published if e.topic == EventTopic.VALENCE_TAGGED]
        assert tagged and tagged[0].payload["urgent"] is True


# --------------------------------------------------------------------------- #
#  Spatial: grid-cell navigation
# --------------------------------------------------------------------------- #
class TestGridCellNavigation:
    async def test_concept_placement_is_deterministic(self):
        first = concept_coord("django middleware")
        second = concept_coord("django middleware")
        assert first == second

    async def test_navigation_finds_path_between_concepts(self):
        navigator = GridCellNavigationUseCase(radius=20)
        navigator.place_concept("home")
        navigator.place_concept("work")
        result = navigator.navigate("home", "work")
        assert result.found is True
        assert result.distance > 0
        assert result.path[0] == navigator.locate("home")
        assert result.path[-1] == navigator.locate("work")

    async def test_blocked_region_blocks_navigation(self):
        navigator = GridCellNavigationUseCase(radius=20)
        navigator.place_concept("home", coord=HexCoord(0, 0))
        navigator.place_concept("far", coord=HexCoord(5, 0))
        navigator.place_concept("wall", coord=HexCoord(2, 0))
        straight = navigator.straight_line(navigator.locate("home"), navigator.locate("far"))
        assert navigator.locate("wall") in straight  # wall sits on the direct line

        navigator.block_region(["wall"])
        result = navigator.navigate("home", "far")
        assert result.found is True
        assert result.distance > 5  # detour around the blocked cell


# --------------------------------------------------------------------------- #
#  Spatial: hexagonal Fourier router
# --------------------------------------------------------------------------- #
class TestFourierRouter:
    async def test_router_detects_dominant_axis(self):
        router = FourierRouterUseCase()
        signal = {HexCoord(i, 0): float(i % 2) for i in range(8)}
        result = router.route(signal)
        assert result.dominant_axis == "q"
        assert result.axis_energy["q"] > 0

    async def test_router_handles_labeled_placements(self):
        router = FourierRouterUseCase()
        placements = {"a": HexCoord(0, 0), "b": HexCoord(3, 0), "c": HexCoord(0, 3)}
        result = router.route_labels(placements, {"a": 1.0, "b": 1.0, "c": 1.0})
        assert result.dominant_axis in {"q", "r", "s"}


# --------------------------------------------------------------------------- #
#  Spatial: H3 fractal zoom
# --------------------------------------------------------------------------- #
class TestHexScaling:
    async def test_zoom_in_descends_hierarchy(self):
        scaling = BoundlessScalingUseCase()
        result = scaling.zoom_in(HexIndex(0, 0), levels=2)
        assert result.resolution == 2
        assert result.area == 49
        assert len(result.children) == 7

    async def test_zoom_out_ascends_to_root(self):
        scaling = BoundlessScalingUseCase()
        deep = HexIndex(0, 0).zoom_in(4)
        result = scaling.zoom_out(deep.index if hasattr(deep, "index") else deep, levels=4)
        assert result.resolution == 0

    async def test_contains_across_resolutions(self):
        scaling = BoundlessScalingUseCase()
        macro = HexIndex(0, 0)
        micro = macro.zoom_in(2)
        assert scaling.contains(macro, micro) is True


# --------------------------------------------------------------------------- #
#  Wiring: coordinator dispatches subcortex loops from cortex events
# --------------------------------------------------------------------------- #
class TestSubcortexCoordinatorWiring:
    async def test_amygdala_reacts_to_memory_stored(self):
        bus = FakeEventBus()
        use_case = AmygdalaUseCase(bus)

        async def on_memory_stored(event: Event) -> None:
            await use_case.tag(event.payload.get("content", ""))

        await bus.subscribe(EventTopic.MEMORY_STORED, on_memory_stored)
        await bus.publish(
            Event(topic=EventTopic.MEMORY_STORED, payload={"content": "security breach detected"})
        )
        assert any(e.topic == EventTopic.VALENCE_TAGGED for e in bus.published)

    async def test_thalamus_reacts_to_user_message(self):
        bus = FakeEventBus()
        registry = FakeCorticalColumnRegistry()
        await registry.get_or_create("col")
        use_case = ThalamicGatingUseCase(registry, bus)

        async def on_user_message(event: Event) -> None:
            payload = event.payload
            await use_case.gate(
                message=payload.get("message", ""),
                priority=float(payload.get("priority", 0.0)),
                emotional_arousal=float(payload.get("emotional_state", {}).get("arousal", 0.0)),
            )

        await bus.subscribe(EventTopic.USER_MESSAGE, on_user_message)
        await bus.publish(
            Event(
                topic=EventTopic.USER_MESSAGE,
                payload={"message": "production is DOWN", "emotional_state": {"arousal": 0.9}},
            )
        )
        assert any(e.topic == EventTopic.ATTENTION_GATED for e in bus.published)
