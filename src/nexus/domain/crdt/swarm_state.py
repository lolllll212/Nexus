"""Swarm state as unified Conflict-Free Replicated Data Types (CRDT).

Integrates:
- G-Counter for monotonic agent heartbeats
- LWW-Register for agent & task status with (tick, agent) deterministic tie-breaking
- OR-Set for task membership and active locks (observed-remove / add-wins)
- State hash with merge-on-read guarantee:
  merge is strictly commutative, associative, and idempotent.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from nexus.domain.crdt.g_counter import GCounter
from nexus.domain.crdt.lww_register import LWWRegister
from nexus.domain.crdt.or_set import ORSet


class LockError(RuntimeError):
    """Base error for CRDT lock failures."""


class LockBlockedError(LockError):
    """Raised when acquiring a lock that is currently held with an active lease."""


class LockState:
    """CRDT-tracked lock state with lease expiry."""

    def __init__(
        self,
        lock_id: str,
        agent: str = "system",
        acquired_at: float | None = None,
        ttl: float = 900.0,
    ) -> None:
        self.lock_id: str = lock_id
        self.agent: str = agent
        self.acquired_at: float = acquired_at if acquired_at is not None else time.time()
        self.ttl: float = float(ttl)

    @property
    def expires_at(self) -> float:
        return self.acquired_at + self.ttl

    def is_expired(self, current_time: float | None = None) -> bool:
        now_ts = current_time if current_time is not None else time.time()
        return now_ts >= self.expires_at

    def merge(self, other: LockState) -> LockState:
        """Merge two lock states using LWW on acquired_at."""
        if other.acquired_at > self.acquired_at:
            return LockState(other.lock_id, other.agent, other.acquired_at, other.ttl)
        elif self.acquired_at > other.acquired_at:
            return LockState(self.lock_id, self.agent, self.acquired_at, self.ttl)
        else:
            chosen_agent = max(self.agent, other.agent)
            return LockState(self.lock_id, chosen_agent, self.acquired_at, max(self.ttl, other.ttl))

    def canonical_repr(self) -> tuple[Any, ...]:
        return (self.lock_id, self.agent, round(self.acquired_at, 3), round(self.ttl, 3))

    def to_dict(self) -> dict[str, Any]:
        return {
            "lock_id": self.lock_id,
            "agent": self.agent,
            "acquired_at": self.acquired_at,
            "ttl": self.ttl,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], lock_id: str | None = None) -> LockState:
        lid = lock_id or data.get("lock_id") or data.get("file") or "unknown"
        acq = data.get("acquired_at")
        if isinstance(acq, (int, float)):
            acq_float = float(acq)
        elif isinstance(acq, str):
            try:
                from datetime import datetime

                acq_float = datetime.fromisoformat(acq).timestamp()
            except Exception:
                try:
                    acq_float = float(acq)
                except Exception:
                    acq_float = 0.0
        else:
            acq_float = 0.0

        ttl_val = float(data.get("ttl", 900.0))
        return cls(
            lock_id=lid,
            agent=data.get("agent", "system"),
            acquired_at=acq_float,
            ttl=ttl_val,
        )


class AgentState:
    """Agent state tracked via CRDT LWW-Registers."""

    def __init__(
        self,
        agent: str,
        status: LWWRegister[str] | None = None,
        current_task: LWWRegister[str | None] | None = None,
        last_heartbeat: LWWRegister[str | None] | None = None,
    ) -> None:
        self.agent: str = agent
        self.status: LWWRegister[str] = status if status is not None else LWWRegister("idle", 0, agent)
        self.current_task: LWWRegister[str | None] = (
            current_task if current_task is not None else LWWRegister(None, 0, agent)
        )
        self.last_heartbeat: LWWRegister[str | None] = (
            last_heartbeat if last_heartbeat is not None else LWWRegister(None, 0, agent)
        )

    def merge(self, other: AgentState) -> AgentState:
        """Merge two agent states field-by-field."""
        return AgentState(
            agent=self.agent,
            status=self.status.merge(other.status),
            current_task=self.current_task.merge(other.current_task),
            last_heartbeat=self.last_heartbeat.merge(other.last_heartbeat),
        )

    @property
    def value(self) -> dict[str, Any]:
        """Backwards-compatible dict view of the agent state."""
        return {
            "agent": self.agent,
            "status": self.status.value,
            "current_task": self.current_task.value,
            "last_heartbeat": self.last_heartbeat.value,
        }

    def canonical_repr(self) -> tuple[Any, ...]:
        return (
            self.agent,
            self.status.canonical_repr(),
            self.current_task.canonical_repr(),
            self.last_heartbeat.canonical_repr(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status.value,
            "current_task": self.current_task.value,
            "last_heartbeat": self.last_heartbeat.value,
            "_crdt": {
                "status": self.status.to_dict(),
                "current_task": self.current_task.to_dict(),
                "last_heartbeat": self.last_heartbeat.to_dict(),
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], agent: str | None = None) -> AgentState:
        ag = agent or data.get("agent", "unknown")
        crdt_meta = data.get("_crdt", {})
        if crdt_meta:
            return cls(
                agent=ag,
                status=LWWRegister.from_dict(crdt_meta["status"]),
                current_task=LWWRegister.from_dict(crdt_meta["current_task"]),
                last_heartbeat=LWWRegister.from_dict(crdt_meta["last_heartbeat"]),
            )
        return cls(
            agent=ag,
            status=LWWRegister(data.get("status", "idle"), 0, ag),
            current_task=LWWRegister(data.get("current_task"), 0, ag),
            last_heartbeat=LWWRegister(data.get("last_heartbeat"), 0, ag),
        )


class TaskState:
    """Task record with LWW-Registers for lifecycle fields."""

    def __init__(
        self,
        task_id: str,
        description: str = "",
        requested_by: str = "",
        for_agent: str = "any",
        priority: str = "medium",
        files: list[str] | None = None,
        acceptance: list[str] | None = None,
        created_at: str | None = None,
        status: LWWRegister[str] | None = None,
        claimed_by: LWWRegister[str | None] | None = None,
        claimed_at: LWWRegister[str | None] | None = None,
        resolved_at: LWWRegister[str | None] | None = None,
        evidence: LWWRegister[str | None] | None = None,
        verified: LWWRegister[bool] | None = None,
        plan_id: str | None = None,
    ) -> None:
        self.task_id: str = task_id
        self.description: str = description
        self.requested_by: str = requested_by
        self.for_agent: str = for_agent
        self.priority: str = priority
        self.files: list[str] = list(files or [])
        self.acceptance: list[str] = list(acceptance or [])
        self.created_at: str | None = created_at
        self.plan_id: str | None = plan_id

        self.status: LWWRegister[str] = (
            status if status is not None else LWWRegister("pending", 0, requested_by or "system")
        )
        self.claimed_by: LWWRegister[str | None] = (
            claimed_by if claimed_by is not None else LWWRegister(None, 0, "system")
        )
        self.claimed_at: LWWRegister[str | None] = (
            claimed_at if claimed_at is not None else LWWRegister(None, 0, "system")
        )
        self.resolved_at: LWWRegister[str | None] = (
            resolved_at if resolved_at is not None else LWWRegister(None, 0, "system")
        )
        self.evidence: LWWRegister[str | None] = (
            evidence if evidence is not None else LWWRegister(None, 0, "system")
        )
        self.verified: LWWRegister[bool] = (
            verified if verified is not None else LWWRegister(False, 0, "system")
        )

    def merge(self, other: TaskState) -> TaskState:
        """Merge two task states using LWW semantics per field."""
        return TaskState(
            task_id=self.task_id,
            description=self.description or other.description,
            requested_by=self.requested_by or other.requested_by,
            for_agent=self.for_agent if self.for_agent != "any" else other.for_agent,
            priority=self.priority or other.priority,
            files=self.files or other.files,
            acceptance=self.acceptance or other.acceptance,
            created_at=self.created_at or other.created_at,
            plan_id=self.plan_id or other.plan_id,
            status=self.status.merge(other.status),
            claimed_by=self.claimed_by.merge(other.claimed_by),
            claimed_at=self.claimed_at.merge(other.claimed_at),
            resolved_at=self.resolved_at.merge(other.resolved_at),
            evidence=self.evidence.merge(other.evidence),
            verified=self.verified.merge(other.verified),
        )

    def canonical_repr(self) -> tuple[Any, ...]:
        return (
            self.task_id,
            self.description,
            self.status.canonical_repr(),
            self.claimed_by.canonical_repr(),
            self.evidence.canonical_repr(),
            self.verified.canonical_repr(),
        )

    @property
    def value(self) -> dict[str, Any]:
        """Backwards-compatible dict view of the task state."""
        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "id": self.task_id,
            "description": self.description,
            "requested_by": self.requested_by,
            "for": self.for_agent,
            "status": self.status.value,
            "priority": self.priority,
            "files": self.files,
            "acceptance": self.acceptance,
            "evidence": self.evidence.value,
            "verified": self.verified.value,
            "created_at": self.created_at,
            "claimed_by": self.claimed_by.value,
            "claimed_at": self.claimed_at.value,
            "resolved_at": self.resolved_at.value,
            "_crdt": {
                "status": self.status.to_dict(),
                "claimed_by": self.claimed_by.to_dict(),
                "claimed_at": self.claimed_at.to_dict(),
                "resolved_at": self.resolved_at.to_dict(),
                "evidence": self.evidence.to_dict(),
                "verified": self.verified.to_dict(),
            },
        }
        if self.plan_id:
            res["plan_id"] = self.plan_id
        return res

    @classmethod
    def from_dict(cls, data: dict[str, Any], task_id: str | None = None) -> TaskState:
        tid = task_id or data.get("id", "task-unknown")
        crdt_meta = data.get("_crdt", {})
        if crdt_meta:
            return cls(
                task_id=tid,
                description=data.get("description", ""),
                requested_by=data.get("requested_by", ""),
                for_agent=data.get("for", "any"),
                priority=data.get("priority", "medium"),
                files=data.get("files", []),
                acceptance=data.get("acceptance", []),
                created_at=data.get("created_at"),
                plan_id=data.get("plan_id"),
                status=LWWRegister.from_dict(crdt_meta["status"]),
                claimed_by=LWWRegister.from_dict(crdt_meta["claimed_by"]),
                claimed_at=LWWRegister.from_dict(crdt_meta["claimed_at"]),
                resolved_at=LWWRegister.from_dict(crdt_meta["resolved_at"]),
                evidence=LWWRegister.from_dict(crdt_meta["evidence"]),
                verified=LWWRegister.from_dict(crdt_meta["verified"]),
            )
        req_by = data.get("requested_by") or "system"
        claim_by = data.get("claimed_by")
        return cls(
            task_id=tid,
            description=data.get("description", ""),
            requested_by=req_by,
            for_agent=data.get("for", "any"),
            priority=data.get("priority", "medium"),
            files=data.get("files", []),
            acceptance=data.get("acceptance", []),
            created_at=data.get("created_at"),
            plan_id=data.get("plan_id"),
            status=LWWRegister(data.get("status", "pending"), 0, req_by),
            claimed_by=LWWRegister(claim_by, 0, claim_by or "system"),
            claimed_at=LWWRegister(data.get("claimed_at"), 0, claim_by or "system"),
            resolved_at=LWWRegister(data.get("resolved_at"), 0, claim_by or "system"),
            evidence=LWWRegister(data.get("evidence"), 0, claim_by or "system"),
            verified=LWWRegister(bool(data.get("verified", False)), 0, "ceo"),
        )


class SwarmState:
    """Composite CRDT representing full swarm coordination state."""

    def __init__(
        self,
        heartbeats: GCounter | None = None,
        agent_status: dict[str, AgentState] | None = None,
        tasks: dict[str, TaskState] | None = None,
        task_membership: ORSet[str] | None = None,
        active_locks: ORSet[str] | None = None,
        lock_states: dict[str, LockState] | None = None,
    ) -> None:
        self.heartbeats: GCounter = heartbeats if heartbeats is not None else GCounter()
        self.agent_status: dict[str, AgentState] = dict(agent_status or {})
        self.tasks: dict[str, TaskState] = dict(tasks or {})
        self.task_membership: ORSet[str] = task_membership if task_membership is not None else ORSet()
        self.active_locks: ORSet[str] = active_locks if active_locks is not None else ORSet()
        self.lock_states: dict[str, LockState] = dict(lock_states or {})

    def record_heartbeat(self, agent: str, tick: int | float = 1, timestamp: str | None = None) -> SwarmState:
        """Increment heartbeat counter and refresh agent active status."""
        self.heartbeats.increment(agent, 1)
        current = self.agent_status.get(agent)
        if current is None:
            current = AgentState(agent)
            self.agent_status[agent] = current
        current.status = current.status.set("active", tick, agent)
        if timestamp:
            current.last_heartbeat = current.last_heartbeat.set(timestamp, tick, agent)
        return self

    def update_agent_status(
        self,
        agent: str,
        status: str,
        tick: int | float,
        current_task: str | None = None,
    ) -> SwarmState:
        """Update an agent's working status using LWW-Register."""
        current = self.agent_status.get(agent)
        if current is None:
            current = AgentState(agent)
            self.agent_status[agent] = current
        current.status = current.status.set(status, tick, agent)
        if current_task is not None:
            current.current_task = current.current_task.set(current_task, tick, agent)
        return self

    def add_task(
        self,
        task_id: str,
        data: dict[str, Any],
        tick: int | float,
        agent: str,
        tag: str | None = None,
    ) -> SwarmState:
        """Add a new task to membership and register its initial state."""
        t = tag or f"{task_id}:{agent}:{tick}"
        self.task_membership.add(task_id, tag=t)
        task_state = TaskState(
            task_id=task_id,
            description=data.get("description", ""),
            requested_by=agent,
            for_agent=data.get("for", "any"),
            priority=data.get("priority", "medium"),
            files=data.get("files", []),
            acceptance=data.get("acceptance", []),
            created_at=data.get("created_at"),
            plan_id=data.get("plan_id"),
            status=LWWRegister(data.get("status", "pending"), tick, agent),
        )
        current = self.tasks.get(task_id)
        self.tasks[task_id] = current.merge(task_state) if current else task_state
        return self

    def update_task(
        self,
        task_id: str,
        updates: dict[str, Any],
        tick: int | float,
        agent: str,
    ) -> SwarmState:
        """Update task data through LWW-Register fields."""
        current = self.tasks.get(task_id)
        if current is None:
            current = TaskState(task_id=task_id)
            self.tasks[task_id] = current

        if "status" in updates:
            current.status = current.status.set(updates["status"], tick, agent)
        if "claimed_by" in updates:
            current.claimed_by = current.claimed_by.set(updates["claimed_by"], tick, agent)
        if "claimed_at" in updates:
            current.claimed_at = current.claimed_at.set(updates["claimed_at"], tick, agent)
        if "resolved_at" in updates:
            current.resolved_at = current.resolved_at.set(updates["resolved_at"], tick, agent)
        if "evidence" in updates:
            current.evidence = current.evidence.set(updates["evidence"], tick, agent)
        if "verified" in updates:
            current.verified = current.verified.set(bool(updates["verified"]), tick, agent)
        if "description" in updates and not current.description:
            current.description = updates["description"]
        return self

    def remove_task(self, task_id: str) -> SwarmState:
        """Tombstone task membership via OR-Set."""
        self.task_membership.remove(task_id)
        return self

    def purge_expired_locks(self, current_time: float | None = None) -> set[str]:
        """Auto-release any locks whose lease duration has elapsed."""
        now_ts = current_time if current_time is not None else time.time()
        active = self.active_locks.read()
        expired: set[str] = set()
        for lid in active:
            st = self.lock_states.get(lid)
            if st is not None and st.is_expired(now_ts):
                expired.add(lid)
        for lid in expired:
            self.active_locks.remove(lid)
            self.lock_states.pop(lid, None)
        return expired

    def is_locked(self, lock_id: str, current_time: float | None = None) -> bool:
        """Return True if lock is currently held and not expired."""
        now_ts = current_time if current_time is not None else time.time()
        self.purge_expired_locks(current_time=now_ts)
        return lock_id in self.active_locks

    def get_lock(self, lock_id: str, current_time: float | None = None) -> LockState | None:
        """Return active LockState if held and not expired, else None."""
        now_ts = current_time if current_time is not None else time.time()
        if not self.is_locked(lock_id, current_time=now_ts):
            return None
        return self.lock_states.get(lock_id)

    def acquire_lock(
        self,
        lock_id: str,
        tag: str | None = None,
        agent: str = "system",
        ttl: float | None = 900.0,
        acquired_at: float | None = None,
        current_time: float | None = None,
    ) -> str:
        """Acquire a lock in the OR-Set with lease duration (default ttl=900s).

        If the lock is held by another agent with an active lease, raises LockBlockedError.
        Expired leases auto-release before acquisition so a dead agent never blocks the swarm.
        """
        now_ts = current_time if current_time is not None else time.time()
        self.purge_expired_locks(current_time=now_ts)

        if lock_id in self.active_locks:
            curr = self.lock_states.get(lock_id)
            if curr is not None and not curr.is_expired(now_ts):
                if curr.agent != agent and curr.agent != "system":
                    rem = curr.expires_at - now_ts
                    raise LockBlockedError(
                        f"Lock '{lock_id}' is held by {curr.agent} (lease expires in {rem:.1f}s)"
                    )

        t = self.active_locks.add(lock_id, tag=tag)
        acq = acquired_at if acquired_at is not None else now_ts
        ttl_val = float(ttl) if ttl is not None else 900.0
        self.lock_states[lock_id] = LockState(
            lock_id=lock_id,
            agent=agent,
            acquired_at=acq,
            ttl=ttl_val,
        )
        return t

    def release_lock(self, lock_id: str) -> set[str]:
        """Release a lock by tombstoning all observed tags."""
        tags = self.active_locks.remove(lock_id)
        self.lock_states.pop(lock_id, None)
        return tags

    def merge(self, other: SwarmState, current_time: float | None = None) -> SwarmState:
        """Commutative and idempotent state-based merge of two SwarmStates."""
        # Merge G-Counter heartbeats
        merged_heartbeats = self.heartbeats.merge(other.heartbeats)

        # Merge Agent Status
        merged_agents: dict[str, AgentState] = {}
        all_agents = set(self.agent_status.keys()) | set(other.agent_status.keys())
        for ag in all_agents:
            a1 = self.agent_status.get(ag)
            a2 = other.agent_status.get(ag)
            if a1 is not None and a2 is not None:
                merged_agents[ag] = a1.merge(a2)
            elif a1 is not None:
                merged_agents[ag] = AgentState.from_dict(a1.to_dict(), agent=ag)
            elif a2 is not None:
                merged_agents[ag] = AgentState.from_dict(a2.to_dict(), agent=ag)

        # Merge Tasks
        merged_tasks: dict[str, TaskState] = {}
        all_tasks = set(self.tasks.keys()) | set(other.tasks.keys())
        for tid in all_tasks:
            t1 = self.tasks.get(tid)
            t2 = other.tasks.get(tid)
            if t1 is not None and t2 is not None:
                merged_tasks[tid] = t1.merge(t2)
            elif t1 is not None:
                merged_tasks[tid] = TaskState.from_dict(t1.to_dict(), task_id=tid)
            elif t2 is not None:
                merged_tasks[tid] = TaskState.from_dict(t2.to_dict(), task_id=tid)

        # Merge OR-Sets
        merged_membership = self.task_membership.merge(other.task_membership)
        merged_locks = self.active_locks.merge(other.active_locks)

        # Merge Lock States
        merged_lock_states: dict[str, LockState] = {}
        all_lock_ids = set(self.lock_states.keys()) | set(other.lock_states.keys())
        for lid in all_lock_ids:
            l1 = self.lock_states.get(lid)
            l2 = other.lock_states.get(lid)
            if l1 is not None and l2 is not None:
                merged_lock_states[lid] = l1.merge(l2)
            elif l1 is not None:
                merged_lock_states[lid] = LockState(l1.lock_id, l1.agent, l1.acquired_at, l1.ttl)
            elif l2 is not None:
                merged_lock_states[lid] = LockState(l2.lock_id, l2.agent, l2.acquired_at, l2.ttl)

        res = SwarmState(
            heartbeats=merged_heartbeats,
            agent_status=merged_agents,
            tasks=merged_tasks,
            task_membership=merged_membership,
            active_locks=merged_locks,
            lock_states=merged_lock_states,
        )
        res.purge_expired_locks(current_time=current_time)
        return res

    def state_hash(self) -> str:
        """Compute deterministic SHA-256 fingerprint of the current state.

        Guaranteed:
        A.merge(B).state_hash() == B.merge(A).state_hash()
        A.merge(A).state_hash() == A.state_hash()
        """
        active_tids = self.task_membership.read()
        canonical_struct = {
            "heartbeats": self.heartbeats.canonical_repr(),
            "agents": sorted((ag, state.canonical_repr()) for ag, state in self.agent_status.items()),
            "tasks": sorted(
                (tid, state.canonical_repr()) for tid, state in self.tasks.items() if tid in active_tids
            ),
            "membership": sorted(str(x) for x in active_tids),
            "locks": sorted(str(x) for x in self.active_locks.read()),
        }
        serialized = json.dumps(canonical_struct, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Serialize complete CRDT state."""
        return {
            "heartbeats": self.heartbeats.to_dict(),
            "agent_status": {k: v.to_dict() for k, v in self.agent_status.items()},
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "task_membership": self.task_membership.to_dict(),
            "active_locks": self.active_locks.to_dict(),
            "lock_states": {k: v.to_dict() for k, v in self.lock_states.items()},
            "state_hash": self.state_hash(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SwarmState:
        """Deserialize from dictionary."""
        hb = GCounter.from_dict(data.get("heartbeats", {}))
        agents = {k: AgentState.from_dict(v, agent=k) for k, v in data.get("agent_status", {}).items()}
        tasks = {k: TaskState.from_dict(v, task_id=k) for k, v in data.get("tasks", {}).items()}
        membership = ORSet.from_dict(data.get("task_membership", {}))
        locks = ORSet.from_dict(data.get("active_locks", {}))
        l_states = {k: LockState.from_dict(v, lock_id=k) for k, v in data.get("lock_states", {}).items()}
        return cls(
            heartbeats=hb,
            agent_status=agents,
            tasks=tasks,
            task_membership=membership,
            active_locks=locks,
            lock_states=l_states,
        )

    def to_nexus_state(self) -> dict[str, Any]:
        """Convert CRDT view to traditional nexus_state.json format."""
        self.purge_expired_locks()
        active_tids = self.task_membership.read()
        task_queue = [self.tasks[tid].to_dict() for tid in sorted(active_tids) if tid in self.tasks]
        agents = {ag: st.to_dict() for ag, st in self.agent_status.items()}
        active_lids = sorted(list(self.active_locks.read()))
        lock_states_dict = {
            lid: self.lock_states[lid].to_dict() for lid in active_lids if lid in self.lock_states
        }
        return {
            "agents": agents,
            "task_queue": task_queue,
            "locks": active_lids,
            "lock_states": lock_states_dict,
            "crdt_hash": self.state_hash(),
        }

    @classmethod
    def from_nexus_state(cls, data: dict[str, Any], tick: int | float = 1) -> SwarmState:
        """Bootstrap CRDT state from traditional nexus_state.json format."""
        agents = {}
        for ag, info in data.get("agents", {}).items():
            agents[ag] = AgentState.from_dict(info, agent=ag)

        tasks = {}
        membership = ORSet[str]()
        for t in data.get("task_queue", []):
            tid = t.get("id")
            if tid:
                membership.add(tid)
                tasks[tid] = TaskState.from_dict(t, task_id=tid)

        locks = ORSet[str]()
        lock_states: dict[str, LockState] = {}
        raw_lock_states = data.get("lock_states", {})
        for lk in data.get("locks", []):
            if isinstance(lk, dict):
                lid = lk.get("lock_id") or lk.get("file") or str(lk)
                locks.add(lid)
                lock_states[lid] = LockState.from_dict(lk, lock_id=lid)
            else:
                lid = str(lk)
                locks.add(lid)
                if lid in raw_lock_states:
                    lock_states[lid] = LockState.from_dict(raw_lock_states[lid], lock_id=lid)
                else:
                    lock_states[lid] = LockState(
                        lock_id=lid, agent="system", acquired_at=time.time(), ttl=900.0
                    )

        return cls(
            heartbeats=GCounter(),
            agent_status=agents,
            tasks=tasks,
            task_membership=membership,
            active_locks=locks,
            lock_states=lock_states,
        )
