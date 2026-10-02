from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from nexus.domain.ports.observability import Metrics, NoopMetrics, NoopTracer, Span, Tracer


class AgentTelemetry:
    """Small, in-memory observability layer for agent loops.

    It records route hits, heal iterations, consensus rounds, and per-agent
    token spend without requiring the full OpenTelemetry stack. When
    NEXUS_OTEL_ENABLED=true the wrappers also emit spans through the current
    tracer so the same data is available to external collectors.
    """

    def __init__(
        self,
        metrics: Metrics | None = None,
        tracer: Tracer | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.enabled = bool(
            enabled if enabled is not None else os.getenv("NEXUS_OTEL_ENABLED", "false").lower() == "true"
        )
        self.metrics = metrics or (NoopMetrics() if not self.enabled else self._default_metrics())
        self.tracer = tracer or (NoopTracer() if not self.enabled else self._default_tracer())
        self._counters: dict[str, float] = defaultdict(float)

    @staticmethod
    def _default_metrics() -> Metrics:
        from nexus.infrastructure.adapters.observability.observability import InMemoryMetrics

        return InMemoryMetrics()

    @staticmethod
    def _default_tracer() -> Tracer:
        from nexus.infrastructure.adapters.observability.observability import LoggingTracer

        return LoggingTracer()

    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Span:
        return self.tracer.span(name, attributes)

    def heal_span(
        self, agent: str, outcome: str = "in_progress", attributes: dict[str, Any] | None = None
    ) -> Span:
        attrs = {"agent": agent, "outcome": outcome, **(attributes or {})}
        return self.span("nexus.heal_iteration", attrs)

    def consensus_span(self, proposal_id: str, author: str, attributes: dict[str, Any] | None = None) -> Span:
        attrs = {"proposal_id": proposal_id, "author": author, **(attributes or {})}
        return self.span("nexus.consensus_round", attrs)

    def record_route(self, route: str, *, agent: str | None = None) -> None:
        labels = {"route": route}
        if agent:
            labels["agent"] = agent
        self.metrics.counter("nexus_route_hits_total", 1.0, labels)
        self._counters["route_hits"] += 1

    def record_heal_cycle(self, outcome: str, duration_seconds: float, *, agent: str | None = None) -> None:
        labels = {"outcome": outcome}
        if agent:
            labels["agent"] = agent
        self.metrics.counter("nexus_heal_cycles_total", 1.0, labels)
        self.metrics.histogram("nexus_heal_duration_seconds", duration_seconds, labels)
        self._counters["heal_cycles"] += 1
        if outcome == "ok":
            self._counters["heal_success"] += 1
        total_heals = self._counters["heal_cycles"]
        if total_heals > 0:
            rate = self._counters["heal_success"] / total_heals
            self.metrics.gauge("nexus_heal_success_rate", rate, {"agent": agent} if agent else None)

    def record_consensus_round(
        self, verdict: str, duration_seconds: float = 0.0, *, agent: str | None = None
    ) -> None:
        labels = {"verdict": verdict}
        if agent:
            labels["agent"] = agent
        self.metrics.counter("nexus_consensus_rounds_total", 1.0, labels)
        if duration_seconds > 0:
            self.metrics.histogram("nexus_consensus_duration_seconds", duration_seconds, labels)
        self._counters["consensus_rounds"] += 1

    def record_token_spend(self, agent: str, tokens: int, *, model: str | None = None) -> None:
        labels = {"agent": agent}
        if model:
            labels["model"] = model
        self.metrics.counter("nexus_token_spend_total", float(tokens), labels)
        self._counters["token_spend"] += float(tokens)

    def render_prometheus(self) -> str:
        return self.metrics.render()


_GLOBAL_AGENT_TELEMETRY: AgentTelemetry | None = None


def get_global_agent_telemetry() -> AgentTelemetry:
    """Return or initialize process-wide AgentTelemetry singleton."""
    global _GLOBAL_AGENT_TELEMETRY
    if _GLOBAL_AGENT_TELEMETRY is None:
        _GLOBAL_AGENT_TELEMETRY = AgentTelemetry()
    return _GLOBAL_AGENT_TELEMETRY
