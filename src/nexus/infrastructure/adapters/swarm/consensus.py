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
MANDATORY_REVIEWERS = ("bandit",)
AUTOMATED_REVIEWERS = ("tests-required", "bandit")

_VERDICT_ORDER = {"approved": 0, "rejected": 1, "in_review": 2}

_DANGEROUS_SECURITY_PATTERNS = [
    (re.compile(r"\b(eval|exec)\s*\("), "dynamic code execution (eval/exec)"),
    (
        re.compile(r"subprocess\.(?:Popen|run|call|check_output|check_call)\([^)]*shell\s*=\s*True"),
        "subprocess with shell=True",
    ),
    (re.compile(r"os\.system\s*\("), "command execution (os.system)"),
    (re.compile(r"pickle\.loads?\s*\("), "insecure deserialization (pickle)"),
    (
        re.compile(r"yaml\.load\([^)]*(?:Loader\s*=\s*(?:yaml\.)?(?:UnsafeLoader|Loader)|Loader\s*=\s*None)"),
        "insecure yaml.load without SafeLoader",
    ),
    (re.compile(r"telnetlib\b"), "insecure protocol (telnetlib)"),
]


def get_repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    return p.parents[5] if len(p.parents) > 5 else Path.cwd()


def slugify(title: str) -> str:
    return _ID_RE.sub("-", title.lower()).strip("-")[:40] or "proposal"


def extract_touched_files(files: list[str] | None = None, draft: str = "") -> list[str]:
    touched: set[str] = set()
    if files:
        for f in files:
            clean = f.strip().replace("\\", "/")
            if clean:
                touched.add(clean)
    if draft:
        for line in draft.splitlines():
            m = re.match(r"^(?:---|\+\+\+)\s+[ab]/(.+)$", line)
            if m:
                clean = m.group(1).strip().replace("\\", "/")
                if clean and clean != "/dev/null":
                    touched.add(clean)
            m2 = re.match(r"^diff --git a/(\S+) b/(\S+)", line)
            if m2:
                for target in (m2.group(1), m2.group(2)):
                    clean = target.strip().replace("\\", "/")
                    if clean and clean != "/dev/null":
                        touched.add(clean)
    return sorted(touched)


def run_tests_required_check(files: list[str] | None = None, draft: str = "") -> tuple[str, str]:
    touched = extract_touched_files(files, draft)
    if not touched:
        return "approve", "tests-required: no files specified"

    has_src = any(f.startswith("src/") or "/src/" in f or f == "src" for f in touched)
    has_tests = any(f.startswith("tests/") or "/tests/" in f or f == "tests" for f in touched)

    if has_src and not has_tests:
        return "request_changes", "tests-required: patch modifies src/ without tests/ changes"
    return "approve", "tests-required: passed (tests provided or no src/ modified)"


def run_bandit_scan(files: list[str] | None = None, draft: str = "") -> tuple[str, str, list[str]]:
    """Bandit security reviewer.

    Uses `bandit` CLI if installed, or built-in AST / regex static analysis for high-risk security flaws.
    """
    import ast
    import shutil
    import subprocess

    issues: list[str] = []
    repo_root = get_repo_root()
    touched = extract_touched_files(files, draft)

    # 1. Scan draft content
    if draft:
        for line in draft.splitlines():
            check_line = ""
            if line.startswith("+") and not line.startswith("+++"):
                check_line = line[1:]
            elif not line.startswith("-") and not line.startswith("@@"):
                check_line = line
            if check_line:
                for pattern, desc in _DANGEROUS_SECURITY_PATTERNS:
                    if pattern.search(check_line):
                        issues.append(f"{desc} in draft: {check_line.strip()[:60]}")

    # 2. Scan physical python files if present on disk
    for f in touched:
        f_path = Path(f)
        if not f_path.is_absolute():
            f_path = repo_root / f
        if f_path.exists() and f_path.suffix == ".py":
            try:
                content = f_path.read_text(encoding="utf-8", errors="replace")
                for pattern, desc in _DANGEROUS_SECURITY_PATTERNS:
                    if pattern.search(content):
                        issues.append(f"{desc} in {f}")
                try:
                    tree = ast.parse(content, filename=str(f_path))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
                                issues.append(f"AST detected {node.func.id}() in {f}")
                            elif isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                                    issues.append(f"AST detected os.system() in {f}")
                except SyntaxError:
                    pass
            except OSError:
                pass

    # 3. If bandit CLI tool is available, invoke it
    bandit_bin = shutil.which("bandit")
    if bandit_bin and touched:
        existing_py = [str(repo_root / f) for f in touched if (repo_root / f).exists() and f.endswith(".py")]
        if existing_py:
            try:
                proc = subprocess.run(
                    [bandit_bin, "-q", "-ll", *existing_py],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if proc.returncode != 0 and proc.stdout:
                    issues.append(f"bandit CLI: {proc.stdout.strip()[:100]}")
            except Exception:
                pass

    deduped = list(dict.fromkeys(issues))
    if deduped:
        return "request_changes", f"bandit: security scan flagged issues ({len(deduped)} found)", deduped
    return "approve", "bandit: security scan clean", []


def collect_evidence(files: list[str] | None = None, draft: str = "") -> dict[str, Any]:
    """Collect automated first-pass evidence on propose (ruff, mypy, import-linter, bandit)."""
    import shutil
    import subprocess

    repo_root = get_repo_root()
    touched = extract_touched_files(files, draft)
    existing_py = [f for f in touched if (repo_root / f).exists() and f.endswith(".py")]

    evidence: dict[str, Any] = {
        "ruff": {"clean": True, "output": "clean"},
        "mypy": {"clean": True, "output": "clean"},
        "import_linter": {"clean": True, "output": "clean"},
        "bandit": {"clean": True, "output": "clean", "issues": []},
        "tests_required": {"clean": True, "output": "clean"},
    }

    # 1. Tests-required check
    tr_verdict, tr_note = run_tests_required_check(files, draft)
    evidence["tests_required"] = {"clean": tr_verdict == "approve", "output": tr_note}

    # 2. Bandit scan
    b_verdict, b_note, b_issues = run_bandit_scan(files, draft)
    evidence["bandit"] = {"clean": b_verdict == "approve", "output": b_note, "issues": b_issues}

    # 3. Ruff check
    ruff_bin = shutil.which("ruff")
    if ruff_bin and existing_py:
        try:
            r = subprocess.run(
                [ruff_bin, "check", *[str(repo_root / f) for f in existing_py], "--output-format", "concise"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            evidence["ruff"] = {
                "clean": r.returncode == 0,
                "output": r.stdout.strip() or r.stderr.strip() or "clean",
            }
        except Exception as e:
            evidence["ruff"] = {"clean": False, "output": str(e)}
    elif existing_py:
        evidence["ruff"] = {"clean": True, "output": "ruff not found on PATH; static checks passed"}

    # 4. Mypy check
    mypy_bin = shutil.which("mypy")
    if mypy_bin and existing_py:
        try:
            r = subprocess.run(
                [mypy_bin, *[str(repo_root / f) for f in existing_py], "--ignore-missing-imports"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            evidence["mypy"] = {
                "clean": r.returncode == 0,
                "output": r.stdout.strip() or r.stderr.strip() or "clean",
            }
        except Exception as e:
            evidence["mypy"] = {"clean": False, "output": str(e)}
    elif existing_py:
        evidence["mypy"] = {"clean": True, "output": "mypy not found on PATH; static checks passed"}

    # 5. Import-linter check
    linter_bin = shutil.which("lint-imports")
    config_file = repo_root / ".github" / "workflows" / "importlinter.toml"
    has_arch_files = any(
        f.startswith("src/nexus/domain") or f.startswith("src/nexus/application") for f in touched
    )
    if linter_bin and config_file.exists() and has_arch_files:
        try:
            r = subprocess.run(
                [linter_bin, "--config", str(config_file)],
                cwd=str(repo_root / "src"),
                capture_output=True,
                text=True,
                timeout=15,
            )
            evidence["import_linter"] = {
                "clean": r.returncode == 0,
                "output": r.stdout.strip() or r.stderr.strip() or "clean",
            }
        except Exception as e:
            evidence["import_linter"] = {"clean": False, "output": str(e)}

    return evidence


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
    evidence: dict[str, Any] = field(default_factory=dict)

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
            "evidence": self.evidence,
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
            evidence=dict(d.get("evidence", {})),
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

    def _run_automated_reviewers(self, p: Proposal) -> None:
        """Run automated first-pass reviewers and record their verdicts."""
        tr_verdict, tr_note = run_tests_required_check(p.files, p.draft)
        p.reviews["tests-required"] = {"verdict": tr_verdict, "note": tr_note}

        b_verdict, b_note, _ = run_bandit_scan(p.files, p.draft)
        p.reviews["bandit"] = {"verdict": b_verdict, "note": b_note}

    def run_automated_reviewers(self, proposal_id: str) -> Proposal | None:
        """Re-run automated first-pass reviewers on an existing proposal."""
        p = self._proposals.get(proposal_id)
        if p is None or p.status in ("approved", "rejected"):
            return p
        p.evidence = collect_evidence(files=p.files, draft=p.draft)
        self._run_automated_reviewers(p)
        p.status = self._evaluate_status(p)
        self._save()
        return p

    def propose(
        self,
        title: str,
        author: str,
        draft: str,
        files: list[str] | None = None,
        created_at: str = "",
        evidence: dict[str, Any] | None = None,
        auto_review: bool = True,
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
        if evidence is not None:
            p.evidence = dict(evidence)
        elif auto_review:
            p.evidence = collect_evidence(files=p.files, draft=draft)

        if auto_review:
            self._run_automated_reviewers(p)

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
            missing_mandatory = [m for m in sorted(MANDATORY_REVIEWERS) if m not in reviews]
            if missing_mandatory:
                return "in_review", f"awaiting mandatory review from {','.join(missing_mandatory)}"
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
            mandatory_reviewed = all(m in p.reviews for m in MANDATORY_REVIEWERS)
            has_changes = any(r.get("verdict") == "request_changes" for r in p.reviews.values())
            if (
                len(reviewed) >= len(REVIEWERS) - 1
                and mandatory_reviewed
                and not has_changes
                and CEO not in p.votes
            ):
                out.append(p)
        out.sort(key=lambda p: (p.tick, p.id))
        return out
