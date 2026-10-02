"""Offline LoRA fine-tuning pipeline on consensus-approved work (Upgrade Space 8).

Trains a local model (RTX 3050 class) on the work the swarm has already judged:
consensus-APPROVED patches become `chosen`, consensus-REJECTED patches become
`rejected` - a DPO-style preference pair. Before the fine-tuned model goes live,
the golden-set eval gates the swap: a candidate whose pass rate regresses against
the current model is blocked, never swapped.

Two things in this module must be right, and both are pure logic:

* Which pairs enter training (`pairs_from_proposals`): reads ONLY approved and
  rejected proposals. An in_review or draft patch has not been judged - training
  on it teaches the model work that may be wrong. Pairs are matched by title
  slug: a title with both an approved and a rejected proposal is a real
  preference signal; a title with only one is not.
* Which model is allowed to go live (`LoRAPipeline.run`): the swap is blocked
  when the candidate's golden-set pass rate regresses below the baseline or the
  absolute floor.

The GPU trainer itself is an adapter concern (the injected `train` callable);
this core never touches torch/peft.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class ProposalLike(Protocol):
    """The slice of a consensus proposal the pipeline needs."""

    id: str
    title: str
    status: str
    draft: str


@dataclass
class PreferencePair:
    """A DPO-style pair: the approved patch is chosen, the rejected one is not."""

    prompt: str
    chosen: str
    rejected: str
    proposal_id: str = ""


@dataclass
class EvalGate:
    """The golden-set comparison between the candidate and the current model."""

    baseline_pass_rate: float
    candidate_pass_rate: float
    passed: bool


@dataclass
class PipelineResult:
    pairs: int = 0
    trained: bool = False
    eval_gate: EvalGate | None = None
    swapped: bool = False
    blocked_reason: str = ""  # "" | no_pairs | train_failed | eval_regressed


def _slug(title: str) -> str:
    return " ".join(title.lower().split())


def pairs_from_proposals(proposals: list[ProposalLike]) -> list[PreferencePair]:
    """Build preference pairs from consensus data - approved=chosen, rejected=rejected.

    Every status that is not a finished judgement (`in_review`, drafts,
    `request_changes`) is ignored: the pipeline reads only approved/rejected
    pairs from the memory store.
    """
    approved: dict[str, ProposalLike] = {}
    rejected: dict[str, ProposalLike] = {}
    for p in proposals:
        if p.status == "approved":
            approved.setdefault(_slug(p.title), p)
        elif p.status == "rejected":
            rejected.setdefault(_slug(p.title), p)
    return [
        PreferencePair(prompt=title, chosen=a.draft, rejected=r.draft, proposal_id=a.id)
        for title, a in approved.items()
        if (r := rejected.get(title)) is not None
    ]


class LoRAPipeline:
    def __init__(
        self,
        pairs_source: Callable[[], list[PreferencePair]],
        train: Callable[[list[PreferencePair], str], bool],
        evaluate: Callable[[str], float],
        baseline_pass_rate: float,
        swap_model: Callable[[str], bool],
        min_pass_rate: float = 0.0,
    ) -> None:
        self._pairs_source = pairs_source
        self._train = train
        self._evaluate = evaluate
        self._baseline = baseline_pass_rate
        self._swap_model = swap_model
        self._min_pass_rate = min_pass_rate

    def run(self, output_dir: str = "lora_out") -> PipelineResult:
        pairs = self._pairs_source()
        if not pairs:
            return PipelineResult(pairs=0, blocked_reason="no_pairs")

        if not self._train(pairs, output_dir):
            return PipelineResult(pairs=len(pairs), blocked_reason="train_failed")

        candidate = self._evaluate(output_dir)
        regressed = candidate < self._baseline or candidate < self._min_pass_rate
        gate = EvalGate(
            baseline_pass_rate=self._baseline,
            candidate_pass_rate=candidate,
            passed=not regressed,
        )
        if regressed:
            # AC: the swap is blocked when the golden-set pass rate regresses.
            return PipelineResult(
                pairs=len(pairs), trained=True, eval_gate=gate, blocked_reason="eval_regressed"
            )

        swapped = self._swap_model(output_dir)
        return PipelineResult(pairs=len(pairs), trained=True, eval_gate=gate, swapped=swapped)
