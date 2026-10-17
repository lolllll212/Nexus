"""Space 9 wiring: heal iterations and consensus rounds emit observability.

The adapters (`scripts/heal_loop.py`, `swarm/consensus.py`) previously kept
their state to themselves. These tests pin the wiring: every consensus
transition records a round, and every heal iteration records a cycle - through
the same `AgentTelemetry` the `/metrics` endpoint and OTEL exporters read.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from nexus.infrastructure.adapters.observability import agent_telemetry as at_module
from nexus.infrastructure.adapters.observability.agent_telemetry import AgentTelemetry
from nexus.infrastructure.adapters.swarm.consensus import ConsensusProtocol

ROOT = Path(__file__).resolve().parents[2]

_DRAFT = "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n"


def _enable_global(monkeypatch) -> AgentTelemetry:
    tele = AgentTelemetry(enabled=True)
    monkeypatch.setattr(at_module, "get_global_agent_telemetry", lambda: tele)
    return tele


def _load_heal_loop():
    spec = importlib.util.spec_from_file_location("nexus_heal_loop", ROOT / "scripts" / "heal_loop.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_consensus_records_a_round_per_transition(monkeypatch, tmp_path) -> None:
    tele = _enable_global(monkeypatch)
    proto = ConsensusProtocol(tmp_path / "consensus_state.json")

    p = proto.propose(
        title="wire consensus telemetry",
        author="xenom",
        draft=_DRAFT,
        files=["src/x.py"],
        auto_review=False,
    )
    proto.review(p.id, "astra", "approve", "lgtm")
    proto.vote(p.id, "ceo", "yes")

    rendered = tele.render_prometheus()
    assert "nexus_consensus_rounds_total" in rendered
    assert rendered.count("nexus_consensus_rounds_total{") == 3
    assert 'agent="xenom"' in rendered
    assert 'agent="astra"' in rendered
    assert 'agent="ceo"' in rendered


def test_consensus_survives_telemetry_failure(monkeypatch, tmp_path) -> None:
    def _boom():
        raise RuntimeError("telemetry backend is down")

    monkeypatch.setattr(at_module, "get_global_agent_telemetry", _boom)
    proto = ConsensusProtocol(tmp_path / "consensus_state.json")

    p = proto.propose(
        title="resilient propose",
        author="xenom",
        draft=_DRAFT,
        files=["src/x.py"],
        auto_review=False,
    )

    assert p.status == "in_review"


def test_heal_iteration_records_ok_cycle(monkeypatch) -> None:
    heal = _load_heal_loop()
    monkeypatch.setattr(heal, "heal_once", lambda dry_run, target, author: 0)
    tele = AgentTelemetry(enabled=True)

    created = heal.heal_iteration(True, "tests/unit", "heal", iteration=1, telemetry=tele)

    rendered = tele.render_prometheus()
    assert created == 0
    assert "nexus_heal_cycles_total" in rendered
    assert 'outcome="ok"' in rendered
    assert 'agent="heal"' in rendered


def test_heal_iteration_records_proposals_outcome(monkeypatch) -> None:
    heal = _load_heal_loop()
    monkeypatch.setattr(heal, "heal_once", lambda dry_run, target, author: 2)
    tele = AgentTelemetry(enabled=True)

    created = heal.heal_iteration(True, "tests/unit", "heal", iteration=2, telemetry=tele)

    assert created == 2
    assert 'outcome="proposals"' in tele.render_prometheus()


def test_heal_iteration_degrades_without_telemetry(monkeypatch) -> None:
    heal = _load_heal_loop()
    monkeypatch.setattr(heal, "heal_once", lambda dry_run, target, author: 0)
    monkeypatch.setattr(heal, "_agent_telemetry", lambda: None)

    assert heal.heal_iteration(True, "tests/unit", "heal", telemetry=None) == 0
