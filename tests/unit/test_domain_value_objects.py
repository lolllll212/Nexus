"""Unit tests for domain value objects.

Covers all 11 value objects / primitives across the domain layer:
- clock (utc_now)
- emotion (EmotionalState, infer_emotional_state)
- hex_fourier (AxisSpectrum, HexSpectrum, hex_fourier_transform)
- hex_grid (HexCoord, HexGrid, hex_line)
- hex_index (HexIndex, hex_index_at)
- identity (Identity, Role)
- schema (JSONSchema)
- synapse (ConnectionType, SynapseConfig)
- valence (ValenceTag)

Verifies:
- Immutability (frozen dataclass immutability raises FrozenInstanceError)
- Validation (input boundaries and error contracts)
- Ordering (comparability and sort contracts where defined)
- Hashing (set membership and dict key stability)
- Domain business logic and properties
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from nexus.domain.value_objects.clock import utc_now
from nexus.domain.value_objects.emotion import EmotionalState, infer_emotional_state
from nexus.domain.value_objects.hex_fourier import (
    AxisSpectrum,
    HexSpectrum,
    hex_fourier_transform,
)
from nexus.domain.value_objects.hex_grid import HexCoord, HexGrid, hex_line
from nexus.domain.value_objects.hex_index import HexIndex, hex_index_at
from nexus.domain.value_objects.identity import Identity, Role
from nexus.domain.value_objects.schema import JSONSchema
from nexus.domain.value_objects.synapse import ConnectionType, SynapseConfig
from nexus.domain.value_objects.valence import ValenceTag

# --------------------------------------------------------------------------- #
# 1. Clock
# --------------------------------------------------------------------------- #


def test_clock_utc_now_returns_timezone_aware_utc():
    now = utc_now()
    assert isinstance(now, datetime)
    assert now.tzinfo is not None
    assert now.tzinfo == timezone.utc


# --------------------------------------------------------------------------- #
# 2. Emotion
# --------------------------------------------------------------------------- #


def test_emotional_state_immutability():
    state = EmotionalState(valence=0.5, arousal=0.2)
    with pytest.raises(FrozenInstanceError):
        state.valence = 0.8  # type: ignore[misc]


def test_emotional_state_validation():
    # Valid bounds
    EmotionalState(valence=-1.0, arousal=0.0)
    EmotionalState(valence=1.0, arousal=1.0)

    # Invalid valence
    with pytest.raises(ValueError, match="valence must be in"):
        EmotionalState(valence=-1.1, arousal=0.5)
    with pytest.raises(ValueError, match="valence must be in"):
        EmotionalState(valence=1.1, arousal=0.5)

    # Invalid arousal
    with pytest.raises(ValueError, match="arousal must be in"):
        EmotionalState(valence=0.0, arousal=-0.1)
    with pytest.raises(ValueError, match="arousal must be in"):
        EmotionalState(valence=0.0, arousal=1.1)


def test_emotional_state_properties_and_blend():
    s1 = EmotionalState(valence=0.4, arousal=0.6, dominant_emotion="happy")
    assert s1.intensity == (0.4 + 0.6) / 2.0

    s2 = EmotionalState(valence=-0.2, arousal=0.8, dominant_emotion="anxious")
    blended = s1.blend(s2, alpha=0.5)
    assert blended.valence == round(0.4 * 0.5 + (-0.2) * 0.5, 3)
    assert blended.arousal == round(0.6 * 0.5 + 0.8 * 0.5, 3)
    assert blended.dominant_emotion == "anxious"


def test_emotional_state_tone_directive():
    calm = EmotionalState(valence=0.0, arousal=0.1)
    assert calm.tone_directive() == ""

    distressed = EmotionalState(valence=-0.5, arousal=0.8)
    directive = distressed.tone_directive()
    assert "distressed" in directive
    assert "agitated" in directive

    positive = EmotionalState(valence=0.5, arousal=0.2)
    assert "positive" in positive.tone_directive()


def test_infer_emotional_state():
    empty_state = infer_emotional_state("")
    assert empty_state.valence == 0.0
    assert empty_state.dominant_emotion == "neutral"

    negative_state = infer_emotional_state("System is broken and awful, panic emergency now!")
    assert negative_state.valence < 0.0
    assert negative_state.arousal > 0.0
    assert negative_state.dominant_emotion == "negative"

    positive_state = infer_emotional_state("Great work! Wonderful, amazing helpful service.")
    assert positive_state.valence > 0.0
    assert positive_state.dominant_emotion == "positive"


# --------------------------------------------------------------------------- #
# 3. Hex Grid (HexCoord, HexGrid, hex_line)
# --------------------------------------------------------------------------- #


def test_hex_coord_immutability():
    coord = HexCoord(q=1, r=2)
    with pytest.raises(FrozenInstanceError):
        coord.q = 3  # type: ignore[misc]


def test_hex_coord_hashing_and_equality():
    c1 = HexCoord(q=2, r=-1)
    c2 = HexCoord(q=2, r=-1)
    c3 = HexCoord(q=1, r=0)

    assert c1 == c2
    assert c1 != c3
    assert hash(c1) == hash(c2)

    coord_set = {c1, c2, c3}
    assert len(coord_set) == 2
    assert c1 in coord_set


def test_hex_coord_ordering():
    coords = [HexCoord(2, 0), HexCoord(0, 1), HexCoord(1, -1), HexCoord(0, 0)]
    sorted_coords = sorted(coords)
    assert sorted_coords[0] == HexCoord(0, 0)
    assert sorted_coords[1] == HexCoord(0, 1)
    assert sorted_coords[2] == HexCoord(1, -1)
    assert sorted_coords[3] == HexCoord(2, 0)


def test_hex_coord_properties_and_neighbors():
    c = HexCoord(q=1, r=2)
    assert c.s == -3
    assert c.cube() == (1, 2, -3)

    origin = HexCoord(0, 0)
    assert origin.distance_to(HexCoord(1, 0)) == 1
    assert origin.distance_to(HexCoord(2, -2)) == 2

    neighbors = list(origin.neighbors())
    assert len(neighbors) == 6
    for n in neighbors:
        assert origin.distance_to(n) == 1

    ring_2 = origin.ring(2)
    assert len(ring_2) == 12
    for rc in ring_2:
        assert origin.distance_to(rc) == 2

    # Ring 0 returns self
    assert origin.ring(0) == [origin]


def test_hex_coord_move_toward():
    start = HexCoord(0, 0)
    target = HexCoord(4, 0)
    step1 = start.move_toward(target, amount=1)
    assert step1 == HexCoord(1, 0)
    assert start.move_toward(target, amount=4) == target
    assert start.move_toward(start, amount=1) == start


def test_hex_line():
    line = hex_line(HexCoord(0, 0), HexCoord(3, 0))
    assert line == [HexCoord(0, 0), HexCoord(1, 0), HexCoord(2, 0), HexCoord(3, 0)]


def test_hex_grid_pathfinding_and_blocking():
    grid = HexGrid(radius=5)
    start = HexCoord(-2, 0)
    goal = HexCoord(2, 0)

    assert grid.contains(start)
    assert not grid.contains(HexCoord(10, 10))

    # Free path
    path = grid.pathfind(start, goal)
    assert path is not None
    assert path[0] == start
    assert path[-1] == goal

    # Block path cells
    grid.block(HexCoord(0, 0))
    grid.block(HexCoord(0, 1))
    grid.block(HexCoord(0, -1))
    grid.set_feature(HexCoord(0, 0), "wall")
    assert grid.is_blocked(HexCoord(0, 0))
    assert grid.feature_at(HexCoord(0, 0)) == "wall"

    detour_path = grid.pathfind(start, goal)
    assert detour_path is not None
    assert HexCoord(0, 0) not in detour_path
    assert HexCoord(0, 1) not in detour_path
    assert HexCoord(0, -1) not in detour_path

    # Unblock
    grid.unblock(HexCoord(0, 0))
    assert not grid.is_blocked(HexCoord(0, 0))


# --------------------------------------------------------------------------- #
# 4. Hex Index (fractal aperture-7 indexing)
# --------------------------------------------------------------------------- #


def test_hex_index_immutability_and_hashing():
    idx = HexIndex(q=1, r=2, resolution=0)
    with pytest.raises(FrozenInstanceError):
        idx.resolution = 1  # type: ignore[misc]

    idx2 = HexIndex(q=1, r=2, resolution=0)
    assert idx == idx2
    assert hash(idx) == hash(idx2)
    assert len({idx, idx2}) == 1


def test_hex_index_hierarchy():
    root = hex_index_at(HexCoord(0, 0), resolution=0)
    assert root.is_root
    assert root.parent() is None
    assert root.relative_area == 1

    children = root.children()
    assert len(children) == 7
    # Center child has exact parent
    center_child = children[0]
    assert center_child.resolution == 1
    assert center_child.parent() == root
    assert root.contains(center_child)

    ancestors = list(center_child.ancestors())
    assert ancestors == [root]

    # Zooming
    deep = root.zoom_in(2)
    assert deep.resolution == 2
    assert deep.zoom_out(2) == root


# --------------------------------------------------------------------------- #
# 5. Hex Fourier (AxisSpectrum, HexSpectrum)
# --------------------------------------------------------------------------- #


def test_hex_fourier_energy_and_dominant_axis():
    s_q = AxisSpectrum(axis="q", magnitudes=[10.0, 0.5, 0.2], dominant_frequency=1)
    # Total energy excludes DC index 0
    assert pytest.approx(s_q.total_energy, rel=1e-5) == 0.7

    s_r = AxisSpectrum(axis="r", magnitudes=[5.0, 2.0, 1.5], dominant_frequency=1)
    assert pytest.approx(s_r.total_energy, rel=1e-5) == 3.5

    s_s = AxisSpectrum(axis="s", magnitudes=[2.0, 0.1, 0.1], dominant_frequency=1)
    assert pytest.approx(s_s.total_energy, rel=1e-5) == 0.2

    hex_spectrum = HexSpectrum(axes={"q": s_q, "r": s_r, "s": s_s})
    assert hex_spectrum.dominant_axis == "r"


def test_hex_fourier_transform():
    signal = {
        HexCoord(0, 0): 1.0,
        HexCoord(1, 0): 2.0,
        HexCoord(2, 0): 1.0,
        HexCoord(0, 1): 0.5,
    }
    spectrum = hex_fourier_transform(signal)
    assert set(spectrum.axes.keys()) == {"q", "r", "s"}
    assert spectrum.dominant_axis in {"q", "r", "s"}


# --------------------------------------------------------------------------- #
# 6. Identity & Role
# --------------------------------------------------------------------------- #


def test_identity_immutability_and_hashing():
    ident = Identity(user_id="alice", tenant_id="tenant-1", role=Role.ADMIN)
    with pytest.raises(FrozenInstanceError):
        ident.user_id = "bob"  # type: ignore[misc]

    ident2 = Identity(user_id="alice", tenant_id="tenant-1", role=Role.ADMIN)
    assert ident == ident2
    assert hash(ident) == hash(ident2)
    assert len({ident, ident2}) == 1


def test_identity_scope_key():
    ident = Identity(user_id="usr_123", tenant_id="acme", role=Role.USER)
    assert ident.scope_key() == "acme:usr_123"


def test_role_enum_values():
    assert Role.ADMIN.value == "admin"
    assert Role.USER.value == "user"
    assert Role.SERVICE.value == "service"
    assert Role.PEER.value == "peer"


# --------------------------------------------------------------------------- #
# 7. JSONSchema
# --------------------------------------------------------------------------- #


def test_json_schema_immutability():
    schema = JSONSchema(
        type="object",
        properties={"text": {"type": "string"}},
        required=["text"],
    )
    with pytest.raises(FrozenInstanceError):
        schema.type = "array"  # type: ignore[misc]


def test_json_schema_validation():
    schema = JSONSchema(
        type="object",
        properties={"name": {"type": "string"}, "count": {"type": "integer"}},
        required=["name"],
    )

    # Valid
    assert schema.validate({"name": "nexus", "count": 10}) == []
    assert schema.validate({"name": "nexus"}) == []

    # Missing required
    errs_missing = schema.validate({"count": 5})
    assert any("Missing required field: name" in err for err in errs_missing)

    # Unexpected field
    errs_unexpected = schema.validate({"name": "nexus", "extra": True})
    assert any("Unexpected field: extra" in err for err in errs_unexpected)


# --------------------------------------------------------------------------- #
# 8. Synapse (ConnectionType, SynapseConfig)
# --------------------------------------------------------------------------- #


def test_connection_type_enum():
    assert ConnectionType.SEMANTIC.value == "semantic"
    assert ConnectionType.TEMPORAL.value == "temporal"
    assert ConnectionType.CAUSAL.value == "causal"
    assert ConnectionType.EMOTIONAL.value == "emotional"
    assert ConnectionType.CONTEXTUAL.value == "contextual"


def test_synapse_config_immutability_and_defaults():
    cfg = SynapseConfig()
    with pytest.raises(FrozenInstanceError):
        cfg.initial_weight = 2.0  # type: ignore[misc]

    assert cfg.initial_weight == 1.0
    assert cfg.hebbian_learning_rate == 0.1
    assert cfg.decay_rate == 0.001
    assert cfg.min_weight == 0.01
    assert cfg.max_weight == 10.0
    assert cfg.strengthening_threshold == 3

    # Hashing
    cfg2 = SynapseConfig()
    assert hash(cfg) == hash(cfg2)
    assert len({cfg, cfg2}) == 1


# --------------------------------------------------------------------------- #
# 9. Valence (ValenceTag)
# --------------------------------------------------------------------------- #


def test_valence_tag_immutability_and_hashing():
    tag = ValenceTag(survival=0.8, utility=0.4, label="infra_failure")
    with pytest.raises(FrozenInstanceError):
        tag.survival = 0.9  # type: ignore[misc]

    tag2 = ValenceTag(survival=0.8, utility=0.4, label="infra_failure")
    assert tag == tag2
    assert hash(tag) == hash(tag2)
    assert len({tag, tag2}) == 1


def test_valence_tag_validation():
    # Valid
    ValenceTag(survival=0.0, utility=0.0)
    ValenceTag(survival=1.0, utility=1.0)

    # Invalid survival
    with pytest.raises(ValueError, match="survival must be in"):
        ValenceTag(survival=-0.1, utility=0.5)
    with pytest.raises(ValueError, match="survival must be in"):
        ValenceTag(survival=1.1, utility=0.5)

    # Invalid utility
    with pytest.raises(ValueError, match="utility must be in"):
        ValenceTag(survival=0.5, utility=-0.1)
    with pytest.raises(ValueError, match="utility must be in"):
        ValenceTag(survival=0.5, utility=1.1)


def test_valence_tag_priority():
    # Survival dominates
    high_survival = ValenceTag(survival=0.9, utility=0.2)
    assert high_survival.priority == 0.9

    # Utility adds when survival is low: max(0.2, 0.5 * 0.8) = 0.4
    high_utility = ValenceTag(survival=0.2, utility=0.8)
    assert high_utility.priority == 0.4
