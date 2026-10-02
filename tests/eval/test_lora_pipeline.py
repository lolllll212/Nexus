"""Tests for the LoRA fine-tuning pipeline (`application/training/lora_pipeline.py`).

The acceptance criteria from plan-001 / Upgrade Space 8, plus the safety
properties they imply:

* The pipeline reads ONLY consensus-approved/rejected pairs - an in_review or
  draft patch never forms a training pair.
* The model swap is blocked when the golden-set pass rate regresses.

Tests live in `tests/eval/` because `tests/unit/` belongs to Tron
(docs/AGENT_COORDINATION.md) and the application layer is mine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nexus.application.training.lora_pipeline import (
    LoRAPipeline,
    PipelineResult,
    PreferencePair,
    pairs_from_proposals,
)


@dataclass
class _Proposal:
    id: str
    title: str
    status: str
    draft: str
    files: list[str] = field(default_factory=list)


def _pair(
    prompt: str = "fix parser", chosen: str = "good diff", rejected: str = "bad diff"
) -> PreferencePair:
    return PreferencePair(prompt=prompt, chosen=chosen, rejected=rejected)


# --------------------------------------------------------------------------
# AC: pipeline reads only consensus-approved/rejected pairs
# --------------------------------------------------------------------------


def test_pairs_match_approved_with_rejected_by_title():
    proposals = [
        _Proposal("p1", "fix parser", "approved", "good diff"),
        _Proposal("p2", "fix parser", "rejected", "bad diff"),
    ]
    pairs = pairs_from_proposals(proposals)

    assert len(pairs) == 1
    assert pairs[0].chosen == "good diff"
    assert pairs[0].rejected == "bad diff"
    assert pairs[0].prompt == "fix parser"
    assert pairs[0].proposal_id == "p1"


def test_unjudged_proposals_never_form_a_pair():
    """THE AC: in_review, drafts and request_changes are not training data. An
    approved + rejected pair forms; the unjudged drafts of the same title never
    appear as the rejected side."""
    proposals = [
        _Proposal("p0", "fix parser", "rejected", "bad diff"),
        _Proposal("p1", "fix parser", "approved", "good diff"),
        _Proposal("p2", "fix parser", "in_review", "unreviewed diff"),
        _Proposal("p3", "fix parser", "request_changes", "blocked diff"),
        _Proposal("p4", "new tool", "in_review", "also unreviewed"),
    ]
    pairs = pairs_from_proposals(proposals)

    assert [p.chosen for p in pairs] == ["good diff"]
    assert [p.rejected for p in pairs] == ["bad diff"]  # the judged one, not the drafts
    assert all(p.rejected != "unreviewed diff" for p in pairs)
    assert all(p.rejected != "blocked diff" for p in pairs)


def test_a_title_with_only_one_verdict_forming_status_has_no_pair():
    approved_only = pairs_from_proposals([_Proposal("p1", "fix parser", "approved", "good diff")])
    rejected_only = pairs_from_proposals([_Proposal("p1", "fix parser", "rejected", "bad diff")])

    assert approved_only == []
    assert rejected_only == []


def test_title_matching_is_whitespace_and_case_insensitive():
    proposals = [
        _Proposal("p1", "Fix  Parser", "approved", "good diff"),
        _Proposal("p2", "fix parser", "rejected", "bad diff"),
    ]
    assert len(pairs_from_proposals(proposals)) == 1


def test_multiple_titles_produce_multiple_pairs():
    proposals = [
        _Proposal("p1", "fix parser", "approved", "good diff"),
        _Proposal("p2", "fix parser", "rejected", "bad diff"),
        _Proposal("p3", "add router", "approved", "router diff"),
        _Proposal("p4", "add router", "rejected", "bad router diff"),
    ]
    pairs = pairs_from_proposals(proposals)

    assert {p.prompt for p in pairs} == {"fix parser", "add router"}
    assert {p.chosen for p in pairs} == {"good diff", "router diff"}


# --------------------------------------------------------------------------
# AC: the swap is blocked on regression
# --------------------------------------------------------------------------


def _pipeline(**overrides):
    defaults: dict = {
        "pairs_source": lambda: [_pair()],
        "train": lambda pairs, out: True,
        "evaluate": lambda out: 0.9,
        "baseline_pass_rate": 0.8,
        "swap_model": lambda out: True,
        "min_pass_rate": 0.0,
    }
    defaults.update(overrides)
    calls = {"pairs": 0, "train": 0, "evaluate": 0, "swap": 0}

    def track(name: str, fn: object):
        def inner(*args):
            calls[name] += 1
            return fn(*args)

        return inner

    pipeline = LoRAPipeline(
        pairs_source=track("pairs", defaults["pairs_source"]),
        train=track("train", defaults["train"]),
        evaluate=track("evaluate", defaults["evaluate"]),
        baseline_pass_rate=defaults["baseline_pass_rate"],
        swap_model=track("swap", defaults["swap_model"]),
        min_pass_rate=defaults["min_pass_rate"],
    )
    return pipeline, calls


def test_candidate_better_than_baseline_is_swapped():
    pipeline, calls = _pipeline(evaluate=lambda out: 0.9, baseline_pass_rate=0.8)

    result = pipeline.run("out")

    assert result.swapped is True
    assert result.blocked_reason == ""
    assert result.eval_gate is not None
    assert result.eval_gate.passed is True
    assert (result.eval_gate.baseline_pass_rate, result.eval_gate.candidate_pass_rate) == (0.8, 0.9)
    assert calls["swap"] == 1


def test_regression_blocks_the_swap():
    """THE AC: candidate pass rate below baseline -> never swapped."""
    pipeline, calls = _pipeline(evaluate=lambda out: 0.5, baseline_pass_rate=0.8)

    result = pipeline.run("out")

    assert result.swapped is False
    assert result.blocked_reason == "eval_regressed"
    assert result.trained is True  # training happened; the swap did not
    assert result.eval_gate is not None and result.eval_gate.passed is False
    assert calls["swap"] == 0


def test_absolute_floor_blocks_even_when_not_a_regression():
    pipeline, calls = _pipeline(evaluate=lambda out: 0.3, baseline_pass_rate=0.2, min_pass_rate=0.5)

    result = pipeline.run("out")

    assert result.swapped is False
    assert result.blocked_reason == "eval_regressed"
    assert calls["swap"] == 0


def test_tie_with_baseline_is_not_a_regression():
    pipeline, _ = _pipeline(evaluate=lambda out: 0.8, baseline_pass_rate=0.8)

    result = pipeline.run("out")

    assert result.swapped is True  # equal is not worse


def test_no_pairs_blocks_before_any_training():
    pipeline, calls = _pipeline(pairs_source=lambda: [])

    result = pipeline.run("out")

    assert result == PipelineResult(pairs=0, blocked_reason="no_pairs")
    assert calls["train"] == 0 and calls["evaluate"] == 0 and calls["swap"] == 0


def test_training_failure_skips_eval_and_swap():
    pipeline, calls = _pipeline(train=lambda pairs, out: False)

    result = pipeline.run("out")

    assert result.blocked_reason == "train_failed"
    assert result.trained is False
    assert result.eval_gate is None
    assert calls["evaluate"] == 0 and calls["swap"] == 0


def test_the_pairs_enter_training_unchanged():
    seen: list = []
    pipeline, _ = _pipeline(train=lambda pairs, out: seen.append(pairs) or True)

    pipeline.run("out")

    assert seen == [[_pair()]]  # the source's pairs, not filtered or rewritten


# --------------------------------------------------------------------------
# Result shape
# --------------------------------------------------------------------------


def test_pipeline_result_defaults():
    result = PipelineResult()
    assert (result.pairs, result.trained, result.swapped, result.blocked_reason) == (0, False, False, "")
    assert result.eval_gate is None
