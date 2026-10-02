from __future__ import annotations

from pathlib import Path

from nexus.infrastructure.adapters.swarm.consensus import (
    ConsensusProtocol,
    Proposal,
)


def test_src_only_patch_auto_request_changes_without_human_review(tmp_path: Path) -> None:
    """A patch modifying src/ without tests/ must be automatically in request_changes."""
    proto = ConsensusProtocol(tmp_path / "consensus.json")
    patch = "--- a/src/nexus/domain/model.py\n+++ b/src/nexus/domain/model.py\n@@ -1 +1 @@\n-# old\n+# new\n"
    p = proto.propose(
        title="Src only change",
        author="tron",
        draft=patch,
        files=["src/nexus/domain/model.py"],
    )

    # Must be in_review immediately without any human reviewer acting
    assert p.status == "in_review"
    assert "tests-required" in p.reviews
    assert p.reviews["tests-required"]["verdict"] == "request_changes"
    assert "tests-required" in p.verdict_reason

    # Human reviews have not been recorded
    assert "astra" not in p.reviews
    assert "tron" not in p.reviews
    assert "xenom" not in p.reviews

    # Even if CEO attempts to approve, request_changes blocks it
    proto.vote(p.id, "ceo", "yes")
    updated = proto.get(p.id)
    assert updated is not None
    assert updated.status == "in_review"
    assert "request_changes from tests-required" in updated.verdict_reason


def test_patch_with_tests_passes_tests_required_rule(tmp_path: Path) -> None:
    """A patch touching both src/ and tests/ passes the tests-required check."""
    proto = ConsensusProtocol(tmp_path / "consensus.json")
    p = proto.propose(
        title="Complete feature",
        author="tron",
        draft="diff --git a/src/a.py b/src/a.py\n+pass\ndiff --git a/tests/test_a.py b/tests/test_a.py\n+pass\n",
        files=["src/nexus/domain/model.py", "tests/unit/test_model.py"],
    )

    assert "tests-required" in p.reviews
    assert p.reviews["tests-required"]["verdict"] == "approve"
    assert "tests-required" not in p.verdict_reason


def test_docs_only_patch_passes_tests_required_rule(tmp_path: Path) -> None:
    """A docs-only patch does not touch src/ and passes tests-required."""
    proto = ConsensusProtocol(tmp_path / "consensus.json")
    p = proto.propose(
        title="Update docs",
        author="astra",
        draft="+docs update\n",
        files=["docs/guide.md"],
    )
    assert p.reviews["tests-required"]["verdict"] == "approve"


def test_diff_without_explicit_files_detects_src_and_tests(tmp_path: Path) -> None:
    """When files are not passed, touched files are extracted from unified diff headers."""
    proto = ConsensusProtocol(tmp_path / "consensus.json")
    diff_src_only = (
        "--- a/src/nexus/application/use_case.py\n+++ b/src/nexus/application/use_case.py\n@@ -1 +1 @@\n"
    )
    p = proto.propose(title="Inferred src", author="xenom", draft=diff_src_only)
    assert p.reviews["tests-required"]["verdict"] == "request_changes"

    diff_with_tests = (
        "--- a/src/nexus/application/use_case.py\n+++ b/src/nexus/application/use_case.py\n"
        "--- a/tests/unit/test_use_case.py\n+++ b/tests/unit/test_use_case.py\n"
    )
    p2 = proto.propose(title="Inferred both", author="xenom", draft=diff_with_tests)
    assert p2.reviews["tests-required"]["verdict"] == "approve"


def test_evidence_attached_on_propose(tmp_path: Path) -> None:
    """Proposals attach ruff, mypy, import-linter, and bandit results as evidence."""
    proto = ConsensusProtocol(tmp_path / "consensus.json")
    p = proto.propose(
        title="Evidence test",
        author="tron",
        draft="print('hello')",
        files=["docs/note.md"],
    )

    assert isinstance(p.evidence, dict)
    assert "ruff" in p.evidence
    assert "mypy" in p.evidence
    assert "import_linter" in p.evidence
    assert "bandit" in p.evidence
    assert "tests_required" in p.evidence

    # Persistence preserves evidence
    proto2 = ConsensusProtocol(tmp_path / "consensus.json")
    loaded = proto2.get(p.id)
    assert loaded is not None
    assert loaded.evidence == p.evidence


def test_bandit_security_scan_detects_eval_and_requests_changes(tmp_path: Path) -> None:
    """Bandit flags dangerous dynamic execution patterns and requests changes."""
    proto = ConsensusProtocol(tmp_path / "consensus.json")
    vulnerable_draft = "def execute_user_query(cmd):\n    return eval(cmd)\n"
    p = proto.propose(
        title="Dangerous patch",
        author="xenom",
        draft=vulnerable_draft,
        files=["src/nexus/eval_tool.py", "tests/unit/test_eval_tool.py"],
    )

    assert "bandit" in p.reviews
    assert p.reviews["bandit"]["verdict"] == "request_changes"
    assert "bandit" in p.verdict_reason
    assert p.status == "in_review"

    # CEO approval is blocked by bandit's request_changes
    proto.review(p.id, "astra", "approve")
    proto.review(p.id, "tron", "approve")
    proto.vote(p.id, "ceo", "yes")
    assert proto.get(p.id).status == "in_review"
    assert "request_changes from bandit" in proto.get(p.id).verdict_reason


def test_bandit_is_mandatory_reviewer_blocks_approval_if_missing(tmp_path: Path) -> None:
    """Bandit is a mandatory reviewer: patch cannot be approved if bandit has not reviewed."""
    proto = ConsensusProtocol(tmp_path / "consensus.json")
    p = proto.propose(
        title="Bypass attempt",
        author="xenom",
        draft="pass\n",
        files=["tests/unit/test_x.py"],
        auto_review=False,
    )

    proto.review(p.id, "astra", "approve")
    proto.review(p.id, "tron", "approve")
    proto.vote(p.id, "ceo", "yes")

    # Missing mandatory reviewer bandit keeps it in_review
    assert proto.get(p.id).status == "in_review"
    assert "awaiting mandatory review from bandit" in proto.get(p.id).verdict_reason

    # Once bandit approves, it approves
    proto.review(p.id, "bandit", "approve", note="clean")
    assert proto.get(p.id).status == "approved"


def test_deterministic_verdict_order_preserved(tmp_path: Path) -> None:
    """Identical reviews and votes in any arrival order yield identical status and reason."""

    def run_sequence(order: list[int], db_name: str) -> Proposal:
        proto = ConsensusProtocol(tmp_path / db_name)
        p = proto.propose(
            title="Deterministic patch",
            author="tron",
            draft="x = 1\n",
            files=["src/nexus/a.py", "tests/unit/test_a.py"],
        )
        actions = [
            ("review", "astra", "approve"),
            ("review", "tron", "approve"),
            ("vote", "tron", "yes"),
            ("vote", "xenom", "yes"),
            ("vote", "ceo", "yes"),
        ]
        for idx in order:
            kind, agent, choice = actions[idx]
            if kind == "review":
                proto.review(p.id, agent, choice)
            else:
                proto.vote(p.id, agent, choice)
        res = proto.get(p.id)
        assert res is not None
        return res

    p1 = run_sequence([0, 1, 2, 3, 4], "db1.json")
    p2 = run_sequence([4, 3, 2, 1, 0], "db2.json")
    p3 = run_sequence([2, 0, 4, 1, 3], "db3.json")

    assert p1.status == p2.status == p3.status == "approved"
    assert p1.verdict_reason == p2.verdict_reason == p3.verdict_reason == "ceo approved"


def test_re_run_automated_reviewers(tmp_path: Path) -> None:
    """run_automated_reviewers refreshes automated reviews and evidence."""
    proto = ConsensusProtocol(tmp_path / "consensus.json")
    p = proto.propose(
        title="Refresh patch",
        author="tron",
        draft="x = 1\n",
        files=["tests/unit/test_x.py"],
        auto_review=False,
    )
    assert "bandit" not in p.reviews
    assert "tests-required" not in p.reviews

    refreshed = proto.run_automated_reviewers(p.id)
    assert refreshed is not None
    assert "bandit" in refreshed.reviews
    assert "tests-required" in refreshed.reviews
    assert "ruff" in refreshed.evidence
