"""The ten Nexus Upgrade Spaces, as one shared product catalog.

The API, React workspace, buildless workspace, and status documentation all
describe the same ten capability areas. Keeping the catalog in the domain
layer prevents those surfaces from drifting into separate, stale lists.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UpgradeSpace:
    """One landed capability area and the evidence a user can inspect."""

    id: int
    name: str
    priority: str
    owner: str
    summary: str
    status: str
    evidence: tuple[str, ...]
    runtime_note: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority,
            "owner": self.owner,
            "summary": self.summary,
            "status": self.status,
            "evidence": list(self.evidence),
            "runtime_note": self.runtime_note,
        }


UPGRADE_SPACES: tuple[UpgradeSpace, ...] = (
    UpgradeSpace(
        id=1,
        name="Semantic memory",
        priority="P0",
        owner="nexus-eng",
        summary="Hybrid cosine + TF-IDF agent memory with a safe lexical fallback.",
        status="landed",
        evidence=(
            "src/nexus/infrastructure/adapters/persistence/agent_memory_store.py",
            "tests/integration/test_memory_semantic.py",
        ),
        runtime_note="Uses embeddings when configured; otherwise retrieval remains TF-IDF based.",
    ),
    UpgradeSpace(
        id=2,
        name="Overnight daemon",
        priority="P0",
        owner="nexus-eng",
        summary="Bounded unattended work with budgets, blackouts, and a kill switch.",
        status="landed",
        evidence=(
            "src/nexus/application/autonomy/overnight_daemon.py",
            "scripts/overnight_daemon.py",
            "tests/eval/test_overnight_daemon.py",
        ),
        runtime_note="Runs only when explicitly started; safety gates remain enforced while idle.",
    ),
    UpgradeSpace(
        id=3,
        name="CRDT swarm state",
        priority="P1",
        owner="nexus-eng",
        summary="Deterministic conflict-free replicated state for cooperative agents.",
        status="landed",
        evidence=(
            "src/nexus/domain/crdt/swarm_state.py",
            "tests/unit/test_crdt.py",
            "tests/unit/test_crdt_locks.py",
        ),
        runtime_note="Pure domain state; transport and persistence stay behind infrastructure adapters.",
    ),
    UpgradeSpace(
        id=4,
        name="Learned router",
        priority="P1",
        owner="nexus-eng",
        summary="Route prediction, logged outcomes, eval feedback, and local short-circuits.",
        status="landed",
        evidence=(
            "src/nexus/infrastructure/adapters/llm/routing_provider.py",
            "tests/integration/test_routing_provider.py",
        ),
        runtime_note="Active when the routing provider is selected; route outcomes feed agent telemetry.",
    ),
    UpgradeSpace(
        id=5,
        name="Consensus reviewers",
        priority="P1",
        owner="nexus-eng",
        summary="Independent reviewer passes that make consequential agent output challengeable.",
        status="landed",
        evidence=(
            "src/nexus/infrastructure/adapters/swarm/consensus.py",
            "tests/integration/test_consensus_reviewers.py",
        ),
        runtime_note="Consensus decisions emit telemetry spans and counters when invoked.",
    ),
    UpgradeSpace(
        id=6,
        name="Swarm dashboard",
        priority="P1",
        owner="nexus-eng",
        summary="A live operational view of agents, budgets, locks, and bridge events.",
        status="landed",
        evidence=(
            "web/src/components/SwarmDashboardView.tsx",
            "scripts/ide_bridge.py",
        ),
        runtime_note="Seeded rows are labelled as a preview until the first bridge snapshot arrives.",
    ),
    UpgradeSpace(
        id=7,
        name="Bridge security",
        priority="P0",
        owner="nexus-eng",
        summary="Authenticated, allow-listed, rate-limited IDE bridge operations.",
        status="landed",
        evidence=(
            "src/nexus/infrastructure/adapters/eventbus/websocket_event_bus.py",
            "scripts/ide_bridge.py",
        ),
        runtime_note="Set NEXUS_BRIDGE_TOKEN to require authentication; browser clients authenticate by message, not URL.",
    ),
    UpgradeSpace(
        id=8,
        name="LoRA pipeline",
        priority="P2",
        owner="nexus-eng",
        summary="Offline adapter-training data, evaluation gates, and a guarded swap seam.",
        status="landed",
        evidence=(
            "src/nexus/application/training/lora_pipeline.py",
            "tests/eval/test_lora_pipeline.py",
        ),
        runtime_note="Training remains an explicit offline workflow; no adapter is swapped automatically.",
    ),
    UpgradeSpace(
        id=9,
        name="Agent telemetry",
        priority="P1",
        owner="nexus-eng",
        summary="Route, heal, consensus, and token telemetry rendered in Prometheus format.",
        status="landed",
        evidence=(
            "src/nexus/infrastructure/adapters/observability/agent_telemetry.py",
            "src/nexus/infrastructure/api/routes/telemetry.py",
            "tests/integration/test_agent_telemetry.py",
        ),
        runtime_note="NEXUS_OTEL_ENABLED controls export; the process-wide instance backs /metrics consistently.",
    ),
    UpgradeSpace(
        id=10,
        name="Docker loop",
        priority="P2",
        owner="nexus-eng",
        summary="A reproducible container profile for long-running Nexus loops.",
        status="landed",
        evidence=("docker-compose.loop.yml",),
        runtime_note="Available as an explicit Compose profile rather than part of the default web stack.",
    ),
)


def upgrade_spaces_catalog() -> dict[str, object]:
    """Return a JSON-serialisable catalog plus honest landed/total counts."""

    spaces = [space.to_dict() for space in UPGRADE_SPACES]
    landed = sum(1 for space in UPGRADE_SPACES if space.status == "landed")
    return {
        "spaces": spaces,
        "summary": {
            "total": len(UPGRADE_SPACES),
            "landed": landed,
            "pending": len(UPGRADE_SPACES) - landed,
        },
    }
