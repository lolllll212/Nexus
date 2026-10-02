"""Unit tests for CRDT distributed locks with lease expiry (task-038).

Verifies:
(a) Expired lease auto-releases so another agent can acquire without deadlock.
(b) Live lease blocks other acquirers (LockBlockedError).
(c) Release tombstones lock correctly via OR-Set semantics.
(d) Locks survive commutative merge from multiple concurrent writers.
(e) Fallback .lock file creation, inspection, and removal in agent_comm.
(f) Clean Architecture: zero infrastructure imports in nexus.domain.crdt.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# Ensure src and scripts are in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import agent_comm  # noqa: E402

from nexus.domain.crdt.swarm_state import (  # noqa: E402
    LockBlockedError,
    LockError,
    SwarmState,
)

# ---------------------------------------------------------------------------
# (a) Expired Lease Auto-Release Tests
# ---------------------------------------------------------------------------


def test_expired_lease_auto_releases_for_new_acquirer():
    """A dead agent's expired lease must not block another agent from acquiring."""
    st = SwarmState()
    base_time = 1000.0

    # Dead agent 'astra' acquires lock with 60s lease at base_time
    st.acquire_lock(
        "src/nexus/domain/ports.py",
        agent="astra",
        ttl=60.0,
        acquired_at=base_time,
        current_time=base_time,
    )
    assert st.is_locked("src/nexus/domain/ports.py", current_time=base_time)
    assert st.get_lock("src/nexus/domain/ports.py", current_time=base_time).agent == "astra"

    # At base_time + 30s (lease still live): astra holds it
    assert not st.get_lock("src/nexus/domain/ports.py", current_time=base_time + 30.0).is_expired(
        base_time + 30.0
    )

    # At base_time + 61s: lease expired -> auto-releases, allowing 'tron' to acquire
    future_time = base_time + 61.0
    assert not st.is_locked("src/nexus/domain/ports.py", current_time=future_time)

    # 'tron' can now acquire without error
    tag = st.acquire_lock(
        "src/nexus/domain/ports.py",
        agent="tron",
        ttl=120.0,
        acquired_at=future_time,
        current_time=future_time,
    )
    assert tag is not None
    assert st.is_locked("src/nexus/domain/ports.py", current_time=future_time)
    curr_lock = st.get_lock("src/nexus/domain/ports.py", current_time=future_time)
    assert curr_lock is not None
    assert curr_lock.agent == "tron"
    assert curr_lock.ttl == 120.0


# ---------------------------------------------------------------------------
# (b) Live Lease Blocking Tests
# ---------------------------------------------------------------------------


def test_live_lease_blocks_other_acquirers():
    """Another agent must be blocked with LockBlockedError while a lease is live."""
    st = SwarmState()
    now_ts = 2000.0

    st.acquire_lock(
        "src/nexus/domain/entities.py",
        agent="tron",
        ttl=300.0,
        acquired_at=now_ts,
        current_time=now_ts,
    )

    # Different agent 'xenom' tries to acquire while lease is active (now_ts + 50s)
    with pytest.raises(LockBlockedError) as exc_info:
        st.acquire_lock(
            "src/nexus/domain/entities.py",
            agent="xenom",
            ttl=100.0,
            current_time=now_ts + 50.0,
        )
    assert "held by tron" in str(exc_info.value)
    assert issubclass(LockBlockedError, LockError)
    assert issubclass(LockBlockedError, RuntimeError)


def test_same_agent_can_renew_live_lease():
    """The holding agent can renew/re-acquire their own live lease without blocking."""
    st = SwarmState()
    t0 = 3000.0
    st.acquire_lock(
        "src/nexus/domain/entities.py",
        agent="tron",
        ttl=100.0,
        acquired_at=t0,
        current_time=t0,
    )

    # 'tron' re-acquires at t0 + 50s with fresh 300s TTL
    t1 = t0 + 50.0
    st.acquire_lock(
        "src/nexus/domain/entities.py",
        agent="tron",
        ttl=300.0,
        acquired_at=t1,
        current_time=t1,
    )

    curr = st.get_lock("src/nexus/domain/entities.py", current_time=t1)
    assert curr is not None
    assert curr.agent == "tron"
    assert curr.acquired_at == t1
    assert curr.ttl == 300.0
    assert curr.expires_at == t1 + 300.0


# ---------------------------------------------------------------------------
# (c) Release Tombstones Tests
# ---------------------------------------------------------------------------


def test_release_lock_tombstones_and_cleans_state():
    """Releasing a lock tombstones it in the OR-Set and clears lock state."""
    st = SwarmState()
    now_ts = 4000.0

    st.acquire_lock("src/nexus/core.py", agent="astra", ttl=600.0, current_time=now_ts)
    assert st.is_locked("src/nexus/core.py", current_time=now_ts)

    # Release lock
    removed_tags = st.release_lock("src/nexus/core.py")
    assert len(removed_tags) >= 1
    assert not st.is_locked("src/nexus/core.py", current_time=now_ts)
    assert st.get_lock("src/nexus/core.py", current_time=now_ts) is None
    assert "src/nexus/core.py" not in st.active_locks


# ---------------------------------------------------------------------------
# (d) Commutative Merge Tests (Multiple Writers)
# ---------------------------------------------------------------------------


def test_locks_survive_commutative_merge_from_multiple_writers():
    """Concurrent locks from multiple nodes merge commutatively and deterministically."""
    t0 = 5000.0

    # Node A acquires lock on file A
    node_a = SwarmState()
    node_a.acquire_lock("file_a.py", agent="tron", ttl=500.0, acquired_at=t0, current_time=t0)

    # Node B acquires lock on file B
    node_b = SwarmState()
    node_b.acquire_lock("file_b.py", agent="astra", ttl=600.0, acquired_at=t0 + 10, current_time=t0 + 10)

    # Node C acquires lock on file C and then releases it
    node_c = SwarmState()
    node_c.acquire_lock("file_c.py", agent="xenom", ttl=300.0, acquired_at=t0, current_time=t0)
    node_c.release_lock("file_c.py")

    # Commutative merge A -> B -> C vs C -> B -> A
    merged_abc = node_a.merge(node_b, current_time=t0 + 20).merge(node_c, current_time=t0 + 20)
    merged_cba = node_c.merge(node_b, current_time=t0 + 20).merge(node_a, current_time=t0 + 20)

    assert merged_abc.state_hash() == merged_cba.state_hash()
    assert merged_abc.is_locked("file_a.py", current_time=t0 + 20)
    assert merged_abc.is_locked("file_b.py", current_time=t0 + 20)
    assert not merged_abc.is_locked("file_c.py", current_time=t0 + 20)

    # Verify lock properties preserved
    lock_a = merged_abc.get_lock("file_a.py", current_time=t0 + 20)
    assert lock_a is not None
    assert lock_a.agent == "tron"
    assert lock_a.ttl == 500.0


def test_merge_purges_expired_leases():
    """Merging states automatically purges any lease that has expired by merge time."""
    t0 = 6000.0
    node_a = SwarmState()
    node_a.acquire_lock("stale_file.py", agent="dead_agent", ttl=50.0, acquired_at=t0, current_time=t0)

    node_b = SwarmState()

    # Merge at t0 + 100s (stale_file has expired)
    merged = node_a.merge(node_b, current_time=t0 + 100.0)
    assert not merged.is_locked("stale_file.py", current_time=t0 + 100.0)
    assert "stale_file.py" not in merged.active_locks


# ---------------------------------------------------------------------------
# (e) agent_comm Helpers & Fallback Lockfile Integration
# ---------------------------------------------------------------------------


def test_agent_comm_lock_helpers_and_fallback_file(tmp_path, monkeypatch):
    """Verify acquire_file_lock, is_file_locked, and release_file_lock handle fallback files."""
    # Direct main_root to tmp_path
    monkeypatch.setattr(agent_comm, "main_root", lambda: tmp_path)
    monkeypatch.setattr(agent_comm, "STATE_FILE", tmp_path / "nexus_state.json")
    monkeypatch.setattr(agent_comm, "CRDT_FILE", tmp_path / "nexus_crdt.json")
    monkeypatch.setattr(agent_comm, "ACTIVITY_LOG", tmp_path / "agent_activity.jsonl")

    target_file = tmp_path / "src" / "nexus" / "domain" / "test_target.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# target", encoding="utf-8")

    rel_path = "src/nexus/domain/test_target.py"

    # 1. Acquire lock
    assert agent_comm.acquire_file_lock(rel_path, agent="tron", ttl=300.0) is True

    # Check fallback .lock file was written
    fallback_lock = agent_comm._lock_file_path(rel_path)
    assert fallback_lock.exists()
    content = fallback_lock.read_text(encoding="utf-8")
    assert "agent: tron" in content

    # Check is_file_locked
    locked, holder = agent_comm.is_file_locked(rel_path)
    assert locked is True
    assert holder == "tron"

    # 2. Competing acquire is blocked
    assert agent_comm.acquire_file_lock(rel_path, agent="xenom", ttl=100.0) is False

    # 3. Release lock
    assert agent_comm.release_file_lock(rel_path, agent="tron") is True
    assert not fallback_lock.exists()

    locked, _ = agent_comm.is_file_locked(rel_path)
    assert locked is False


# ---------------------------------------------------------------------------
# (f) Clean Architecture Domain Independence
# ---------------------------------------------------------------------------


def test_clean_architecture_domain_independence():
    """Domain CRDT files must never import from nexus.infrastructure."""
    crdt_dir = REPO_ROOT / "src" / "nexus" / "domain" / "crdt"
    for py_file in crdt_dir.glob("*.py"):
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
