from __future__ import annotations

import asyncio
from pathlib import Path

from nexus.domain.ports.llm_provider import LLMProvider
from nexus.infrastructure.adapters.llm.routing_provider import (
    Complexity,
    LearnedClassifier,
    LearnedRouter,
    RoutingProvider,
)


class MockLLM(LLMProvider):
    def __init__(self, reply: str, fail: bool = False) -> None:
        self.reply = reply
        self.fail = fail
        self.calls = 0

    async def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
    ) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider unavailable")
        return self.reply

    async def extract_structured(self, content: str, schema: dict, instructions: str = "") -> dict:
        self.calls += 1
        return {}


def test_learned_classifier_training_and_convergence(tmp_path: Path) -> None:
    """Classifier trains on labeled prompts and shifts probabilities accordingly."""
    weights_path = tmp_path / "weights.json"
    clf = LearnedClassifier(weights_path=weights_path, learning_rate=0.2)

    # Train on routine formatting tasks (low)
    for _ in range(15):
        clf.update("format code and fix trailing whitespace", target=Complexity.LOW, quality=1.0)
        clf.update("fix formatting in setup.cfg", target=Complexity.LOW, quality=0.9)

    # Train on complex architecture tasks (high)
    for _ in range(15):
        clf.update(
            "prove invariant for CRDT merge protocol under network partition",
            target=Complexity.HIGH,
            quality=1.0,
        )
        clf.update(
            "architect distributed consensus state machine with vector clocks",
            target=Complexity.HIGH,
            quality=0.95,
        )

    prob_low = clf.predict_proba("fix formatting in main.py")
    prob_high = clf.predict_proba("prove distributed CRDT consistency invariant")

    assert prob_low < 0.4
    assert prob_high > 0.6
    assert clf.predict("fix formatting in main.py") is Complexity.LOW
    assert clf.predict("prove distributed CRDT consistency invariant") is Complexity.HIGH


def test_router_persists_learned_weights_across_restarts(tmp_path: Path) -> None:
    """Learned weights and sample counts survive disk persistence and reload."""
    weights_path = tmp_path / "router_weights.json"

    primary = MockLLM("primary-answer")
    local = MockLLM("local-answer")

    rp1 = RoutingProvider(
        primary=primary,
        local=local,
        weights_path=weights_path,
        cost_aware=True,
    )

    # Train rp1 with feedback
    for _ in range(10):
        rp1.record_feedback("rename variable x to y", route="local", accepted=True, quality=0.95)
        rp1.record_feedback(
            "refactor consensus protocol to avoid race conditions",
            route="primary",
            accepted=True,
            quality=0.98,
        )

    assert weights_path.exists()
    seen1 = rp1.learned_router.classifier.samples_seen  # type: ignore[union-attr]
    assert seen1 >= 20

    # Simulate restart by instantiating a new RoutingProvider loading from the same path
    rp2 = RoutingProvider(
        primary=primary,
        local=local,
        weights_path=weights_path,
        cost_aware=True,
    )

    clf2 = rp2.learned_router.classifier  # type: ignore[union-attr]
    assert clf2.samples_seen == seen1
    assert clf2.weights == rp1.learned_router.classifier.weights  # type: ignore[union-attr]

    # Predictions match across instances
    prompt = "refactor consensus protocol to avoid race conditions"
    assert rp2.learned_router.classifier.predict_proba(prompt) == rp1.learned_router.classifier.predict_proba(prompt)  # type: ignore[union-attr]


def test_cost_aware_routing_tradeoff(tmp_path: Path) -> None:
    """Cost-aware router considers latency and cost weights to optimize routing."""
    weights_path = tmp_path / "weights.json"
    clf = LearnedClassifier(weights_path=weights_path)

    # Set up router with high cost sensitivity
    router_frugal = LearnedRouter(classifier=clf, cost_aware=True, cost_weight=0.6, latency_weight=0.2)
    # Routine task with moderate complexity
    decision, metrics = router_frugal.route_decision("write a helper function to validate email strings")
    assert decision is Complexity.LOW
    assert metrics["u_local"] >= metrics["u_primary"]

    # Critical architecture query routes to primary even when cost-aware
    decision_arch, _ = router_frugal.route_decision(
        "refactor security auth architecture and prove crdt consistency"
    )
    assert decision_arch is Complexity.HIGH


def test_speculative_short_circuit_for_local_tier(tmp_path: Path) -> None:
    """When speculative short-circuit is enabled, valid local reply saves primary call."""
    primary = MockLLM("primary-heavy-output")
    local_high = MockLLM("local-fast-good-output")

    rp = RoutingProvider(
        primary=primary,
        local_high=local_high,
        weights_path=tmp_path / "weights.json",
        speculative=True,
        force_route=Complexity.HIGH,
    )

    reply = asyncio.run(rp.complete([{"role": "user", "content": "refactor the memory engine"}]))
    assert reply == "local-fast-good-output"
    assert primary.calls == 0
    assert local_high.calls == 1
    assert rp.route_log[-1]["route"] == "local-speculative"
    assert rp.learned_router.stats["speculative_hits"] == 1  # type: ignore[union-attr]


def test_speculative_short_circuit_falls_through_on_empty(tmp_path: Path) -> None:
    """If speculative local attempt produces empty/error reply, it falls through to primary."""
    primary = MockLLM("primary-fallback-output")
    local_high = MockLLM("")  # Empty speculative attempt

    rp = RoutingProvider(
        primary=primary,
        local_high=local_high,
        weights_path=tmp_path / "weights.json",
        speculative=True,
        force_route=Complexity.HIGH,
    )

    reply = asyncio.run(rp.complete([{"role": "user", "content": "refactor the memory engine"}]))
    assert reply == "primary-fallback-output"
    assert local_high.calls >= 1
    assert primary.calls == 1
    assert rp.route_log[-1]["route"] == "primary"


def test_train_from_route_log_with_eval_feedback(tmp_path: Path) -> None:
    """Router trains on its own route_log history and updates weights."""
    primary = MockLLM("premium-result")
    local = MockLLM("local-result")

    rp = RoutingProvider(
        primary=primary,
        local=local,
        weights_path=tmp_path / "route_weights.json",
    )

    # Populate route_log through queries
    asyncio.run(rp.complete([{"role": "user", "content": "fix typo in doc"}]))
    asyncio.run(
        rp.complete([{"role": "user", "content": "refactor security architecture and crdt invariant"}])
    )

    assert len(rp.route_log) == 2
    initial_samples = rp.learned_router.classifier.samples_seen  # type: ignore[union-attr]

    # Feed eval harness acceptance outcomes
    accepted_outcomes = {0: True, 1: True}
    trained_count = rp.train_from_route_log(accepted_outcomes)

    assert trained_count == 2
    assert rp.learned_router.classifier.samples_seen == initial_samples + 2  # type: ignore[union-attr]
