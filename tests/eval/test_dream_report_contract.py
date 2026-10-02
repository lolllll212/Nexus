"""The `nexus dream` report must only read attributes the result dataclasses have.

Found while wiring the overnight daemon (task-030): the dream cycle ran, did its
work, and then crashed building its own report - `cli.py` read
`result.pruning.pruned` and `result.consolidation.consolidated`, and NEITHER
attribute exists (`PruningResult` has `vectors_pruned`/`synapses_pruned`;
`ConsolidationResult` has `connections_strengthened`/`emotionally_charged`).
Every `nexus dream` run was dying at report time, unnoticed, because nothing
exercised that path.

Same relationship as the docs and prompt contracts, one level deeper: `cli.py`'s
report and the dreaming result dataclasses are two sources that must agree.
Checked generically by extraction - every `result.<phase>.<attr>` access in
`_cmd_dream` is resolved against the real dataclass with `getattr` - not a
hand-list of fields.
"""

from __future__ import annotations

import re
from pathlib import Path

from nexus.application.subcortex.dreaming.compress import CompressionResult
from nexus.application.subcortex.dreaming.consolidate import ConsolidationResult
from nexus.application.subcortex.dreaming.prune import PruningResult
from nexus.application.subcortex.dreaming.simulate import SimulationResult

CLI = Path(__file__).resolve().parents[2] / "src" / "nexus" / "cli.py"

# phase name in the dream session result -> the dataclass it must match.
_PHASE_TYPES = {
    "compression": CompressionResult,
    "pruning": PruningResult,
    "simulation": SimulationResult,
    "consolidation": ConsolidationResult,
}
# `result.<phase>.<attr>` - the report's per-phase attribute reads.
_PHASE_ATTR = re.compile(r"result\.(compression|pruning|simulation|consolidation)\.(\w+)")

# result.session_id etc. live on the dream session itself, not a phase dataclass.
_SESSION_ATTR = re.compile(r"result\.(\w+)")


def _func_body(text: str, name: str) -> str:
    """The body of one top-level function, so the chat report's reads of a
    DIFFERENT result type (lines below _cmd_dream) are not mistaken for dream reads."""
    match = re.search(rf"^(?:async )?def {name}\(.*?(?=^(?:async )?def |\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(0) if match else ""


def _has(cls, attr: str) -> bool:
    """Dataclass fields without defaults do not exist as class attributes."""
    return attr in getattr(cls, "__dataclass_fields__", {}) or hasattr(cls, attr)


def _report_accesses() -> set[tuple[str, str]]:
    """(phase, attr) for every per-phase read in the dream report builder."""
    text = CLI.read_text(encoding="utf-8")
    # `_cmd_dream` is a thin wrapper; the report is built in `_run_dream`.
    body = _func_body(text, "_run_dream")
    return set(_PHASE_ATTR.findall(body))


def test_the_extraction_actually_finds_phase_reads():
    """If the extraction rots, the real check below passes on nothing."""
    accesses = _report_accesses()
    assert len(accesses) >= 6, f"only {len(accesses)} phase reads found - extraction is stale"
    assert (
        "pruning",
        "vectors_pruned",
    ) in accesses, "the fixed pruning read is missing from cli.py - did the bug come back?"


def test_the_dream_report_only_reads_attributes_that_exist():
    """A report read that no dataclass has is a crash at report time."""
    broken = []
    for phase, attr in sorted(_report_accesses()):
        cls = _PHASE_TYPES.get(phase)
        if cls is None:
            broken.append(f"  result.{phase}.{attr}: no known dataclass for phase {phase}")
        elif not _has(cls, attr):
            fields = ", ".join(f.name for f in cls.__dataclass_fields__.values())
            broken.append(f"  result.{phase}.{attr}: {cls.__name__} has none of it (fields: {fields})")
    assert not broken, (
        "cli.py's dream report reads attributes the result dataclasses do not have -\n"
        "this crashes every `nexus dream` run at report time:\n" + "\n".join(broken)
    )


def test_the_dream_session_result_carries_every_reported_field():
    """The session-level reads (session_id, recall_delta, ...) must exist too."""
    from nexus.application.subcortex.dreaming.dream_session import DreamSessionResult

    text = CLI.read_text(encoding="utf-8")
    session_reads = {
        attr for attr in _SESSION_ATTR.findall(_func_body(text, "_run_dream")) if "." not in attr
    }
    missing = [
        f"  result.{attr}: DreamSessionResult has none of it"
        for attr in sorted(session_reads)
        if not _has(DreamSessionResult, attr)
    ]
    assert not missing, "cli.py reads session fields that do not exist:\n" + "\n".join(missing)
