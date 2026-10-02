"""Critique-and-consensus protocol for multi-agent code changes.

Flow: propose -> review -> vote -> verdict. No patch is written to disk
without consensus: Zenom drafts the implementation, Astra reviews it for
security/logic flaws, and the CEO casts the deciding vote.

Deterministic verdict rules (same review/vote set -> same outcome, regardless
of arrival order):
- `in_review` while any reviewer has issued `request_changes`.
- `rejected` iff the CEO voted no, or a majority of worker voters voted no,
  or a tie exists with no CEO vote (safe default: contested patches never
  apply autonomously).
- `approved` iff no request_changes outstanding AND the CEO voted yes - the
  CEO is the deciding vote, exactly one is required.
- Workers can veto (majority no) but only the CEO can approve.

All listings sort canonically (tick, id); ids are content-addressed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ID_RE = re.compile(r"[^a-z0-9]+")

REVIEWERS = ("astra", "tron", "xenom")
CEO = "ceo"

_VERDICT_ORDER = {"approved": 0, "rejected": 1, "in_review": 2}


def slugify(title: str) -> str:
    return _ID_RE.sub("-", title.lower()).strip("-")[:40] or "proposal"


@dataclass
class Proposal:
    """A code-change proposal moving through consensus."""

    id: str
    title: str
    author: str
    draft: str
    files: list[str] = field(default_factory=list)
    status: str = "in_review"
    reviews: dict[str, dict[str, str]] = field(default_factory=dict)
    votes: dict[str, str] = field(default_factory=dict)
    tick: int = 0
    created_at: str = ""
    verdict: str = ""
    verdict_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "draft": self.draft,
            "files": sorted(self.files),
            "status": self.status,
            "reviews": self.reviews,
            "votes": self.votes,
            "tick": self.tick,
            "created_at": self.created_at,
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Proposal:
        return cls(
            id=d["id"],
            title=d["title"],
            author=d["author"],
            draft=d["draft"],
            files=list(d.get("files", [])),
            status=d.get("status", "in_review"),
            reviews=dict(d.get("reviews", {})),
            votes=dict(d.get("votes", {})),
            tick=d.get("tick", 0),
            created_at=d.get("created_at", ""),
            verdict=d.get("verdict", ""),
            verdict_reason=d.get("verdict_reason", ""),
        )


class ConsensusProtocol:
    """Consensus state machine over a JSON file in the main worktree."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._proposals: dict[str, Proposal] = {}
        self._tick = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for d in data.get("proposals", []):
            p = Proposal.from_dict(d)
            self._proposals[p.id] = p
        self._tick = data.get("next_tick", len(self._proposals))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self._proposals.values(), key=lambda p: (p.tick, p.id))
        self.path.write_text(
            json.dumps(
                {"proposals": [p.to_dict() for p in ordered], "next_tick": self._tick},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def propose(
        self,
        title: str,
        author: str,
        draft: str,
        files: list[str] | None = None,
        created_at: str = "",
    ) -> Proposal:
        pid = f"{slugify(title)}-{hashlib.sha256(draft.encode('utf-8')).hexdigest()[:8]}"
        existing = self._proposals.get(pid)
        if existing is not None:
            return existing
        self._tick += 1
        p = Proposal(
            id=pid,
            title=title,
            author=author,
            draft=draft,
            files=files or [],
            tick=self._tick,
            created_at=created_at,
        )
        p.status = self._evaluate_status(p)
        self._proposals[pid] = p
        self._save()
        return p

    def review(self, proposal_id: str, reviewer: str, verdict: str, note: str = "") -> Proposal | None:
        p = self._proposals.get(proposal_id)
        if p is None or p.status in ("approved", "rejected"):
            return p if p is not None else None
        if verdict not in ("approve", "request_changes"):
            return p
        p.reviews[reviewer] = {"verdict": verdict, "note": note}
        p.status = self._evaluate_status(p)
        self._save()
        return p

    def vote(self, proposal_id: str, agent: str, choice: str) -> Proposal | None:
        p = self._proposals.get(proposal_id)
        if p is None or p.status in ("approved", "rejected"):
            return p if p is not None else None
        if choice not in ("yes", "no", "abstain"):
            return p
        p.votes[agent] = choice
        p.status = self._evaluate_status(p)
        self._save()
        return p

    def _evaluate_status(self, p: Proposal) -> str:
        verdict, reason = self._resolve(p)
        p.verdict_reason = reason
        return verdict

    def _resolve(self, p: Proposal) -> tuple[str, str]:
        # Deterministic: evaluate from canonical snapshots of reviews/votes.
        reviews = {k: p.reviews[k]["verdict"] for k in sorted(p.reviews)}
        votes = {k: p.votes[k] for k in sorted(p.votes)}
        changes = [k for k, v in reviews.items() if v == "request_changes"]
        if changes:
            return "in_review", f"request_changes from {','.join(changes)}"
        worker_votes = {k: v for k, v in votes.items() if k != CEO}
        yes = [k for k, v in worker_votes.items() if v == "yes"]
        no = [k for k, v in worker_votes.items() if v == "no"]
        if len(no) > len(yes):
            return "rejected", f"majority no ({','.join(no)})"
        ceo_vote = votes.get(CEO)
        if no and len(no) == len(yes) and ceo_vote is None:
            return "rejected", "tie breaks to rejection without CEO"
        if ceo_vote == "no":
            return "rejected", "ceo voted no"
        if ceo_vote == "yes":
            return "approved", "ceo approved"
        return "in_review", f"awaiting CEO vote ({len(yes)} yes / {len(no)} no)"

    def resolve(self, proposal_id: str) -> tuple[str, str] | None:
        """Public (status, reason) for a proposal. None if unknown id."""
        p = self._proposals.get(proposal_id)
        if p is None:
            return None
        return self._resolve(p)

    def get(self, proposal_id: str) -> Proposal | None:
        return self._proposals.get(proposal_id)

    def list_proposals(self, status: str | None = None) -> list[Proposal]:
        proposals = [p for p in self._proposals.values() if status is None or p.status == status]
        proposals.sort(key=lambda p: (p.tick, p.id))
        return proposals

    def needs_attention(self) -> list[Proposal]:
        """In-review proposals with all reviewer verdicts in, awaiting the CEO vote."""
        out: list[Proposal] = []
        for p in self.list_proposals(status="in_review"):
            reviewed = {k for k in REVIEWERS if k in p.reviews}
            if len(reviewed) >= len(REVIEWERS) - 1 and CEO not in p.votes:
                out.append(p)
        out.sort(key=lambda p: (p.tick, p.id))
        return out
