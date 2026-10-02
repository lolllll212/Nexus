"""Plan-first gate for multi-agent implementation work.

Agents make a bounded plan (to-do list with files) BEFORE implementing:
- Bounds the thinking: steps are capped, so cost per unit of work is capped
  too - no open-ended re-thinking mid-flight.
- Prevents mid-set file edits that error out: every step names the files it
  will touch, and the gate (`is_covered`) refuses edits to files no active
  plan covers.

Deterministic rules (same plan -> same state, regardless of arrival order):
- A plan starts as `draft`; `begin()` moves it to `in_progress`.
- Steps are done strictly in order (`complete_step` refuses to skip ahead).
- Steps are capped at `max_steps` (default 5) - `add_step` beyond the cap is
  rejected unless the plan is abandoned and re-planned.
- While `in_progress`, the plan is FROZEN: no new steps, no file changes to
  the step list. Editing a file outside the plan requires abandoning it.
- `finish()` requires every step done.

All listings sort canonically (tick, id); ids are content-addressed.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_MAX_STEPS = 5
# Roots an agent plan may touch - mirrors the ide_bridge editable roots.
PLAN_EDITABLE_ROOTS = ("src", "tests", "scripts", "docs", "plugins", "config")

_STATUSES = ("draft", "in_progress", "done", "abandoned")


def slugify(title: str) -> str:
    return hashlib.sha256(title.lower().encode("utf-8")).hexdigest()[:12]


@dataclass
class PlanStep:
    """One bounded unit of work with the files it will touch."""

    description: str
    files: list[str] = field(default_factory=list)
    done: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "files": list(self.files),
            "done": self.done,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlanStep:
        return cls(
            description=d["description"],
            files=list(d.get("files", [])),
            done=bool(d.get("done")),
            note=d.get("note", ""),
        )


@dataclass
class Plan:
    """A bounded, plan-first to-do list for one agent."""

    title: str
    agent: str
    id: str = ""
    status: str = "draft"
    steps: list[PlanStep] = field(default_factory=list)
    max_steps: int = DEFAULT_MAX_STEPS
    tick: int = 0
    created_at: str = ""
    finished_at: str = ""
    abandon_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "agent": self.agent,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "max_steps": self.max_steps,
            "tick": self.tick,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "abandon_reason": self.abandon_reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Plan:
        return cls(
            title=d["title"],
            agent=d["agent"],
            id=d["id"],
            status=d.get("status", "draft"),
            steps=[PlanStep.from_dict(s) for s in d.get("steps", [])],
            max_steps=d.get("max_steps", DEFAULT_MAX_STEPS),
            tick=d.get("tick", 0),
            created_at=d.get("created_at", ""),
            finished_at=d.get("finished_at", ""),
            abandon_reason=d.get("abandon_reason", ""),
        )

    def files(self) -> list[str]:
        out: list[str] = []
        for s in self.steps:
            for f in s.files:
                if f not in out:
                    out.append(f)
        return out

    def next_step(self) -> int | None:
        """Index of the first not-done step, or None when all are done."""
        for i, s in enumerate(self.steps):
            if not s.done:
                return i
        return None

    def all_done(self) -> bool:
        return bool(self.steps) and all(s.done for s in self.steps)

    def progress(self) -> str:
        done = sum(1 for s in self.steps if s.done)
        return f"{done}/{len(self.steps)}"


class PlanningBoard:
    """Plan-first state machine over a JSON file in the main worktree."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._plans: dict[str, Plan] = {}
        self._tick = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for d in data.get("plans", []):
            p = Plan.from_dict(d)
            self._plans[p.id] = p
        self._tick = data.get("next_tick", len(self._plans))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self._plans.values(), key=lambda p: (p.tick, p.id))
        self.path.write_text(
            json.dumps(
                {"plans": [p.to_dict() for p in ordered], "next_tick": self._tick},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def create_plan(
        self,
        title: str,
        agent: str,
        steps: list[tuple[str, list[str]]],
        max_steps: int = DEFAULT_MAX_STEPS,
        created_at: str = "",
    ) -> tuple[Plan, str | None]:
        """Create a draft plan. Returns (plan, error) - error when over the
        step cap or when an identical draft already exists."""
        if len(steps) > max_steps:
            return Plan(title=title, agent=agent, max_steps=max_steps), (
                f"plan rejected: {len(steps)} steps exceeds the cap of {max_steps} - "
                f"split the work or raise --max-steps explicitly"
            )
        if not steps:
            return Plan(title=title, agent=agent), "plan rejected: a plan needs at least one step"
        pid = f"plan-{slugify(title)}"
        existing = self._plans.get(pid)
        if existing is not None and existing.status in ("draft", "in_progress"):
            return existing, f"plan {pid} already {existing.status} - finish or abandon it first"
        self._tick += 1
        p = Plan(
            title=title,
            agent=agent,
            id=pid,
            steps=[PlanStep(description=d, files=fs) for d, fs in steps],
            max_steps=max_steps,
            tick=self._tick,
            created_at=created_at or datetime.now(UTC).isoformat(),
        )
        self._plans[pid] = p
        self._save()
        return p, None

    def begin(self, plan_id: str) -> tuple[Plan | None, str | None]:
        """draft -> in_progress. Freezes the plan."""
        p = self._plans.get(plan_id)
        if p is None:
            return None, f"unknown plan {plan_id}"
        if p.status != "draft":
            return p, f"plan is {p.status}, not draft"
        p.status = "in_progress"
        self._save()
        return p, None

    def complete_step(self, plan_id: str, note: str = "") -> tuple[Plan | None, str | None]:
        """Mark the FIRST not-done step done. Skipping ahead is refused - a
        plan executed out of order is exactly the mid-set edit mess this gate
        exists to prevent."""
        p = self._plans.get(plan_id)
        if p is None:
            return None, f"unknown plan {plan_id}"
        if p.status != "in_progress":
            return p, f"plan is {p.status}, not in_progress - begin it first"
        idx = p.next_step()
        if idx is None:
            return p, "all steps already done - finish the plan"
        p.steps[idx].done = True
        p.steps[idx].note = note
        self._save()
        return p, None

    def add_step(
        self, plan_id: str, description: str, files: list[str] | None = None
    ) -> tuple[Plan | None, str | None]:
        """Add a step. Only drafts accept new steps - an in_progress plan is
        frozen: discovering unplanned work mid-flight means abandoning the
        plan and re-planning with the full picture."""
        p = self._plans.get(plan_id)
        if p is None:
            return None, f"unknown plan {plan_id}"
        if p.status == "in_progress":
            return p, (
                "plan is in_progress and FROZEN - no new steps mid-flight; "
                "abandon it and re-plan with what you now know"
            )
        if p.status in ("done", "abandoned"):
            return p, f"plan is {p.status}"
        if len(p.steps) >= p.max_steps:
            return p, f"step cap reached ({p.max_steps}) - re-plan instead of growing"
        p.steps.append(PlanStep(description=description, files=files or []))
        self._save()
        return p, None

    def abandon(self, plan_id: str, reason: str = "") -> tuple[Plan | None, str | None]:
        p = self._plans.get(plan_id)
        if p is None:
            return None, f"unknown plan {plan_id}"
        if p.status in ("done", "abandoned"):
            return p, f"plan already {p.status}"
        p.status = "abandoned"
        p.abandon_reason = reason
        p.finished_at = datetime.now(UTC).isoformat()
        self._save()
        return p, None

    def finish(self, plan_id: str) -> tuple[Plan | None, str | None]:
        """in_progress -> done. Requires every step done."""
        p = self._plans.get(plan_id)
        if p is None:
            return None, f"unknown plan {plan_id}"
        if p.status != "in_progress":
            return p, f"plan is {p.status}, not in_progress"
        if not p.all_done():
            idx = p.next_step()
            assert idx is not None
            return p, f"cannot finish: step {idx + 1} not done ({p.steps[idx].description[:60]})"
        p.status = "done"
        p.finished_at = datetime.now(UTC).isoformat()
        self._save()
        return p, None

    def get(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def list_plans(self, status: str | None = None, agent: str | None = None) -> list[Plan]:
        plans = [
            p
            for p in self._plans.values()
            if (status is None or p.status == status) and (agent is None or p.agent == agent)
        ]
        plans.sort(key=lambda p: (p.tick, p.id))
        return plans

    # ------------------------------------------------------------------
    # The gate
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize(path: str) -> str:
        """Forward slashes, no leading './', no trailing slash. Deterministic."""
        p = path.replace("\\", "/").strip()
        while p.startswith("./"):
            p = p[2:]
        return posixpath.normpath(p).rstrip("/") if p else p

    def is_covered(self, path: str) -> tuple[bool, Plan | None, str]:
        """The gate: is this file covered by an in_progress plan's steps?

        Returns (covered, plan, reason). A file is covered when it matches a
        planned file exactly, or lives under a planned directory. Plans may
        only touch PLAN_EDITABLE_ROOTS.
        """
        norm = self._normalize(path)
        root = norm.split("/")[0] if norm else ""
        if root not in PLAN_EDITABLE_ROOTS:
            return (
                False,
                None,
                f"'{root or norm}' is outside the editable roots ({', '.join(PLAN_EDITABLE_ROOTS)})",
            )
        for p in self.list_plans(status="in_progress"):
            for f in p.files():
                fnorm = self._normalize(f)
                if norm == fnorm or norm.startswith(fnorm.rstrip("/") + "/"):
                    return True, p, f"covered by {p.id} ({p.progress()})"
        return (
            False,
            None,
            (
                f"no in_progress plan covers '{norm}' - plan before you edit "
                f"(python scripts/plan_comm.py plan ... then begin, then edit)"
            ),
        )


def check_file(path: str, board: PlanningBoard) -> tuple[bool, str]:
    """Standalone gate check. Returns (allowed, reason)."""
    covered, plan, reason = board.is_covered(path)
    if covered:
        assert plan is not None
        return True, f"ALLOWED: {reason}"
    return False, reason
