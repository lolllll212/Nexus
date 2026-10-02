"""Tests for Swarm CRDT primitives, composite SwarmState, and SwarmStatePort.

Verifies:
1. G-Counter, LWW-Register, and OR-Set mathematical properties (commutative, associative, idempotent).
2. SwarmState merge-on-read determinism and state_hash invariance across write order permutations.
3. Clean Architecture: zero imports from nexus.infrastructure in nexus.domain.crdt and ports.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nexus.domain.crdt.g_counter import GCounter
from nexus.domain.crdt.lww_register import LWWRegister
from nexus.domain.crdt.or_set import ORSet
from nexus.domain.crdt.swarm_state import SwarmState
from nexus.domain.ports.swarm_state import SwarmStatePort

# ---------------------------------------------------------------------------
# G-Counter Tests
# ---------------------------------------------------------------------------


def test_g_counter_basic_increments():
    gc = GCounter()
    assert gc.value == 0
    assert gc.get("tron") == 0

    gc.increment("tron", 2)
    gc.increment("astra", 3)
    gc.increment("tron", 1)

    assert gc.get("tron") == 3
    assert gc.get("astra") == 3
    assert gc.value == 6


def test_g_counter_negative_amount_raises():
    gc = GCounter()
    with pytest.raises(ValueError):
        gc.increment("tron", -1)

    with pytest.raises(ValueError):
        GCounter({"tron": -5})


def test_g_counter_merge_properties():
    # Commutative: A.merge(B) == B.merge(A)
    a = GCounter({"tron": 5, "astra": 2})
    b = GCounter({"tron": 3, "astra": 4, "xenom": 1})

    ab = a.merge(b)
    ba = b.merge(a)

    assert ab.value == 10  # max(5,3) + max(2,4) + max(0,1) = 5 + 4 + 1
    assert ab == ba
    assert ab.counts == {"tron": 5, "astra": 4, "xenom": 1}

    # Idempotent: A.merge(A) == A
    assert a.merge(a) == a

    # Associative: (A.merge(B)).merge(C) == A.merge(B.merge(C))
    c = GCounter({"tron": 7, "ceo": 10})
    left = (a.merge(b)).merge(c)
    right = a.merge(b.merge(c))
    assert left == right
    assert left.value == 22


def test_g_counter_serialization():
    gc = GCounter({"tron": 10, "astra": 5})
    d = gc.to_dict()
    restored = GCounter.from_dict(d)
    assert gc == restored
    assert restored.value == 15


# ---------------------------------------------------------------------------
# LWW-Register Tests
# ---------------------------------------------------------------------------


def test_lww_register_tick_dominance():
    r1 = LWWRegister(value="pending", tick=10, agent="tron")
    r2 = LWWRegister(value="claimed", tick=20, agent="astra")

    # Higher tick wins regardless of merge order
    assert r1.merge(r2).value == "claimed"
    assert r2.merge(r1).value == "claimed"


def test_lww_register_agent_tie_break():
    # Same tick, different agent: lexicographical tie-break
    r1 = LWWRegister(value="val_tron", tick=100, agent="tron")
    r2 = LWWRegister(value="val_astra", tick=100, agent="astra")

    # 'tron' > 'astra'
    assert r1.merge(r2).value == "val_tron"
    assert r2.merge(r1).value == "val_tron"
    assert r1.merge(r2) == r2.merge(r1)


def test_lww_register_identical_tick_and_agent_tie_break():
    # Same tick and same agent: deterministic value tie-break
    r1 = LWWRegister(value="beta", tick=10, agent="tron")
    r2 = LWWRegister(value="alpha", tick=10, agent="tron")

    m1 = r1.merge(r2)
    m2 = r2.merge(r1)
    assert m1.value == "beta"
    assert m1 == m2


def test_lww_register_properties():
    a = LWWRegister("A", 1, "tron")
    b = LWWRegister("B", 2, "astra")
    c = LWWRegister("C", 3, "xenom")

    # Commutative
    assert a.merge(b) == b.merge(a)
    # Idempotent
    assert a.merge(a) == a
    # Associative
    assert (a.merge(b)).merge(c) == a.merge(b.merge(c))


def test_lww_register_serialization():
    reg = LWWRegister({"status": "resolved", "evidence": "pytest ok"}, 42, "tron")
    d = reg.to_dict()
    restored = LWWRegister.from_dict(d)
    assert reg == restored
    assert restored.value["status"] == "resolved"


# ---------------------------------------------------------------------------
# OR-Set Tests
# ---------------------------------------------------------------------------


def test_or_set_add_and_remove():
    s = ORSet[str]()
    assert len(s) == 0

    s.add("task-001")
    assert "task-001" in s
    assert len(s) == 1

    s.remove("task-001")
    assert "task-001" not in s
    assert len(s) == 0


def test_or_set_add_wins_on_concurrent_merge():
    # Replica A and B both start with task-001 (tag t1)
    tag_t1 = "tag-initial"
    replica_a = ORSet[str](add_set=[("task-001", tag_t1)])
    replica_b = ORSet[str](add_set=[("task-001", tag_t1)])

    # Replica B removes task-001 (tombstones tag_t1)
    replica_b.remove("task-001")
    assert "task-001" not in replica_b

    # Concurrently, Replica A re-adds task-001 (generates new tag_t2)
    tag_t2 = "tag-re-added"
    replica_a.add("task-001", tag=tag_t2)
    assert "task-001" in replica_a

    # Merge A and B: tag_t2 is not tombstoned, so task-001 SURVIVES (Add-Wins!)
    merged_ab = replica_a.merge(replica_b)
    merged_ba = replica_b.merge(replica_a)

    assert "task-001" in merged_ab
    assert "task-001" in merged_ba
    assert merged_ab == merged_ba


def test_or_set_properties():
    a = ORSet[str](add_set=[("x", "1"), ("y", "2")])
    b = ORSet[str](add_set=[("y", "2"), ("z", "3")], remove_set=[("x", "1")])
    c = ORSet[str](add_set=[("w", "4")])

    # Commutative
    assert a.merge(b) == b.merge(a)
    # Idempotent
    assert a.merge(a) == a
    # Associative
    assert (a.merge(b)).merge(c) == a.merge(b.merge(c))


def test_or_set_serialization():
    s = ORSet[str]()
    s.add("alpha", "t1")
    s.add("beta", "t2")
    s.remove("alpha")

    d = s.to_dict()
    restored = ORSet.from_dict(d)
    assert s == restored
    assert "beta" in restored
    assert "alpha" not in restored


# ---------------------------------------------------------------------------
# SwarmState & State Hash Tests
# ---------------------------------------------------------------------------


def test_swarm_state_merge_commutativity_and_idempotence():
    s1 = SwarmState()
    s1.record_heartbeat("tron", tick=1)
    s1.add_task("task-001", {"description": "Fix bug", "priority": "high"}, tick=1, agent="ceo")

    s2 = SwarmState()
    s2.record_heartbeat("astra", tick=1)
    s2.update_task("task-001", {"status": "claimed", "claimed_by": "tron"}, tick=2, agent="tron")

    # Commutative
    m1 = s1.merge(s2)
    m2 = s2.merge(s1)

    assert m1.state_hash() == m2.state_hash()
    assert m1.heartbeats.value == 2
    assert m1.tasks["task-001"].value["status"] == "claimed"

    # Idempotent
    assert m1.merge(m1).state_hash() == m1.state_hash()


def test_swarm_state_write_order_invariance():
    """CRITICAL ACCEPTANCE: Same action set from any write order produces identical state_hash."""

    # We will simulate 3 different replicas that apply the same logical actions
    # in 3 completely different orderings and merge them.

    def build_history_order_1():
        st = SwarmState()
        # 1. heartbeats
        st.record_heartbeat("tron", tick=1)
        st.record_heartbeat("astra", tick=2)
        # 2. task added
        st.add_task("task-001", {"description": "Build CRDT"}, tick=10, agent="ceo")
        # 3. lock acquired & released
        st.acquire_lock("lock:src/nexus/domain/crdt")
        st.active_locks.remove("lock:src/nexus/domain/crdt")
        # 4. task claimed
        st.update_task("task-001", {"status": "claimed", "claimed_by": "tron"}, tick=20, agent="tron")
        # 5. task resolved
        st.update_task("task-001", {"status": "resolved", "evidence": "tests pass"}, tick=30, agent="tron")
        return st

    def build_history_order_2():
        # Disjoint sub-states merged together
        part1 = SwarmState()
        part1.record_heartbeat("astra", tick=2)
        part1.add_task("task-001", {"description": "Build CRDT"}, tick=10, agent="ceo")
        part1.update_task("task-001", {"status": "resolved", "evidence": "tests pass"}, tick=30, agent="tron")

        part2 = SwarmState()
        part2.record_heartbeat("tron", tick=1)
        part2.update_task("task-001", {"status": "claimed", "claimed_by": "tron"}, tick=20, agent="tron")
        part2.acquire_lock("lock:src/nexus/domain/crdt")
        part2.active_locks.remove("lock:src/nexus/domain/crdt")

        return part1.merge(part2)

    def build_history_order_3():
        # Reverse chronological arrival
        partA = SwarmState()
        partA.update_task("task-001", {"status": "resolved", "evidence": "tests pass"}, tick=30, agent="tron")
        partA.record_heartbeat("astra", tick=2)

        partB = SwarmState()
        partB.add_task("task-001", {"description": "Build CRDT"}, tick=10, agent="ceo")
        partB.update_task("task-001", {"status": "claimed", "claimed_by": "tron"}, tick=20, agent="tron")
        partB.record_heartbeat("tron", tick=1)
        partB.acquire_lock("lock:src/nexus/domain/crdt")
        partB.active_locks.remove("lock:src/nexus/domain/crdt")

        return partB.merge(partA)

    s1 = build_history_order_1()
    s2 = build_history_order_2()
    s3 = build_history_order_3()

    hash1 = s1.state_hash()
    hash2 = s2.state_hash()
    hash3 = s3.state_hash()

    assert hash1 == hash2, f"State hashes differed between order 1 and 2: {hash1} != {hash2}"
    assert hash2 == hash3, f"State hashes differed between order 2 and 3: {hash2} != {hash3}"


def test_swarm_state_nexus_state_interoperability():
    # Bootstrap from standard nexus_state dict
    nexus_dict = {
        "agents": {
            "tron": {"status": "active", "current_task": "task-001"},
            "astra": {"status": "idle", "current_task": None},
        },
        "task_queue": [
            {"id": "task-001", "description": "Test task", "status": "claimed", "claimed_by": "tron"}
        ],
        "locks": ["file:foo.py"],
    }

    crdt_state = SwarmState.from_nexus_state(nexus_dict, tick=1)
    assert "task-001" in crdt_state.task_membership
    assert crdt_state.tasks["task-001"].value["claimed_by"] == "tron"
    assert "file:foo.py" in crdt_state.active_locks

    # Convert back to nexus_state format
    exported = crdt_state.to_nexus_state()
    assert "crdt_hash" in exported
    assert exported["agents"]["tron"]["status"] == "active"
    assert len(exported["task_queue"]) == 1
    assert exported["task_queue"][0]["id"] == "task-001"
    assert exported["locks"] == ["file:foo.py"]


# ---------------------------------------------------------------------------
# Architecture Boundary Test
# ---------------------------------------------------------------------------


def test_clean_architecture_domain_independence():
    """CRITICAL ACCEPTANCE: no import from nexus.infrastructure anywhere in the new domain code."""
    crdt_dir = Path(__file__).resolve().parents[2] / "src" / "nexus" / "domain" / "crdt"
    port_file = Path(__file__).resolve().parents[2] / "src" / "nexus" / "domain" / "ports" / "swarm_state.py"

    files_to_check = list(crdt_dir.glob("*.py")) + [port_file]
    assert len(files_to_check) >= 4, f"Expected domain files to check, found: {files_to_check}"

    for py_file in files_to_check:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(
                        "nexus.infrastructure"
                    ), f"Domain file {py_file.name} illegally imports {alias.name} at line {node.lineno}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not node.module.startswith(
                        "nexus.infrastructure"
                    ), f"Domain file {py_file.name} illegally imports from {node.module} at line {node.lineno}"


# ---------------------------------------------------------------------------
# SwarmStatePort Contract Test
# ---------------------------------------------------------------------------


def test_swarm_state_port_conformance():
    class InMemorySwarmStateAdapter(SwarmStatePort):
        def __init__(self):
            self._state = SwarmState()

        def get_state(self) -> SwarmState:
            return self._state

        def save_state(self, state: SwarmState) -> None:
            self._state = state

        def merge(self, remote_state: SwarmState) -> SwarmState:
            self._state = self._state.merge(remote_state)
            return self._state

        def record_heartbeat(self, agent: str, tick: int | float = 1) -> SwarmState:
            return self._state.record_heartbeat(agent, tick)

        def update_agent_status(
            self, agent: str, status: str, tick: int | float, current_task: str | None = None
        ) -> SwarmState:
            return self._state.update_agent_status(agent, status, tick, current_task)

        def add_task(self, task_id: str, data: dict, tick: int | float, agent: str) -> SwarmState:
            return self._state.add_task(task_id, data, tick, agent)

        def update_task(self, task_id: str, updates: dict, tick: int | float, agent: str) -> SwarmState:
            return self._state.update_task(task_id, updates, tick, agent)

        def remove_task(self, task_id: str) -> SwarmState:
            return self._state.remove_task(task_id)

        def get_state_hash(self) -> str:
            return self._state.state_hash()

    adapter = InMemorySwarmStateAdapter()
    assert adapter.get_state_hash() is not None
    adapter.record_heartbeat("tron")
    assert adapter.get_state().heartbeats.get("tron") == 1
