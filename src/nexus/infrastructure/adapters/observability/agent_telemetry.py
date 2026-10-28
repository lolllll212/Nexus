from __future__ import annotations

import os
import threading
from collections import defaultdict
from typing import Any

from nexus.domain.ports.observability import Metrics, NoopMetrics, NoopTracer, Span, Tracer


class AgentTelemetry:
    """Small, in-memory observability layer for agent loops.

    It records route hits, heal iterations, consensus rounds, and per-agent
    token spend without requiring the full OpenTelemetry stack. When
    NEXUS_OTEL_ENABLED=true the wrappers also emit spans through the current
    tracer so the same data is available to external collectors.

    ``enabled`` is deliberately reactive. The process-wide instance may be
    created before configuration is final (or a test/deployment may turn the
    gate on later); flipping it must replace the *default* no-op adapters with
    real ones instead of silently discarding every later measurement.
    Explicitly injected adapters are never replaced.
    """

    def __init__(
        self,
        metrics: Metrics | None = None,
        tracer: Tracer | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._metrics_explicit = metrics is not None
        self._tracer_explicit = tracer is not None
        self._enabled = bool(
            enabled if enabled is not None else os.getenv("NEXUS_OTEL_ENABLED", "false").lower() == "true"
        )
        self._metrics = metrics or (self._default_metrics() if self._enabled else NoopMetrics())
        self._tracer = tracer or (self._default_tracer() if self._enabled else NoopTracer())
        self._counters: dict[str, float] = defaultdict(float)

    @staticmethod
    def _default_metrics() -> Metrics:
        from nexus.infrastructure.adapters.observability.observability import InMemoryMetrics

        return InMemoryMetrics()

    @staticmethod
    def _default_tracer() -> Tracer:
        from nexus.infrastructure.adapters.observability.observability import LoggingTracer

        return LoggingTracer()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        with self._lock:
            self._enabled = bool(value)
            if self._enabled:
                if not self._metrics_explicit and isinstance(self._metrics, NoopMetrics):
                    self._metrics = self._default_metrics()
                if not self._tracer_explicit and isinstance(self._tracer, NoopTracer):
                    self._tracer = self._default_tracer()
            else:
                if not self._metrics_explicit:
                    self._metrics = NoopMetrics()
                if not self._tracer_explicit:
                    self._tracer = NoopTracer()

    @property
    def metrics(self) -> Metrics:
        return self._metrics

    @metrics.setter
    def metrics(self, value: Metrics) -> None:
        with self._lock:
            self._metrics = value
            self._metrics_explicit = True

    @property
    def tracer(self) -> Tracer:
        return self._tracer

    @tracer.setter
    def tracer(self, value: Tracer) -> None:
        with self._lock:
            self._tracer = value
            self._tracer_explicit = True

    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Span:
        if not self._enabled:
            return NoopTracer().span(name, attributes)
        return self._tracer.span(name, attributes)

    def heal_span(
        self, agent: str, outcome: str = "in_progress", attributes: dict[str, Any] | None = None
    ) -> Span:
        attrs = {"agent": agent, "outcome": outcome, **(attributes or {})}
        return self.span("nexus.heal_iteration", attrs)

    def consensus_span(self, proposal_id: str, author: str, attributes: dict[str, Any] | None = None) -> Span:
        attrs = {"proposal_id": proposal_id, "author": author, **(attributes or {})}
        return self.span("nexus.consensus_round", attrs)

    def record_route(self, route: str, *, agent: str | None = None) -> None:
        if not self._enabled:
            return
        labels = {"route": route}
        if agent:
            labels["agent"] = agent
        with self._lock:
            self._metrics.counter("nexus_route_hits_total", 1.0, labels)
            self._counters["route_hits"] += 1

    def record_heal_cycle(self, outcome: str, duration_seconds: float, *, agent: str | None = None) -> None:
        if not self._enabled:
            return
        labels = {"outcome": outcome}
        if agent:
            labels["agent"] = agent
        with self._lock:
            self._metrics.counter("nexus_heal_cycles_total", 1.0, labels)
            self._metrics.histogram("nexus_heal_duration_seconds", duration_seconds, labels)
            self._counters["heal_cycles"] += 1
            if outcome == "ok":
                self._counters["heal_success"] += 1
            total_heals = self._counters["heal_cycles"]
            if total_heals > 0:
                rate = self._counters["heal_success"] / total_heals
                self._metrics.gauge("nexus_heal_success_rate", rate, {"agent": agent} if agent else None)

    def record_consensus_round(
        self, verdict: str, duration_seconds: float = 0.0, *, agent: str | None = None
    ) -> None:
        if not self._enabled:
            return
        labels = {"verdict": verdict}
        if agent:
            labels["agent"] = agent
        with self._lock:
            self._metrics.counter("nexus_consensus_rounds_total", 1.0, labels)
            if duration_seconds > 0:
                self._metrics.histogram("nexus_consensus_duration_seconds", duration_seconds, labels)
            self._counters["consensus_rounds"] += 1

    def record_token_spend(self, agent: str, tokens: int, *, model: str | None = None) -> None:
        if not self._enabled:
            return
        labels = {"agent": agent}
        if model:
            labels["model"] = model
        with self._lock:
            self._metrics.counter("nexus_token_spend_total", float(tokens), labels)
            self._counters["token_spend"] += float(tokens)

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-friendly view that status surfaces can trust."""

        with self._lock:
            counters = {
                "route_hits": int(self._counters["route_hits"]),
                "heal_cycles": int(self._counters["heal_cycles"]),
                "heal_success": int(self._counters["heal_success"]),
                "consensus_rounds": int(self._counters["consensus_rounds"]),
                "token_spend": int(self._counters["token_spend"]),
            }
            heal_success_rate = (
                round(counters["heal_success"] / counters["heal_cycles"], 4)
                if counters["heal_cycles"] > 0
                else None
            )
            return {
                "enabled": self._enabled,
                "metrics_backend": type(self._metrics).__name__,
                "tracer_backend": type(self._tracer).__name__,
                "counters": counters,
                "heal_success_rate": heal_success_rate,
            }

    def render_prometheus(self) -> str:
        if not self._enabled:
            return ""
        return self._metrics.render()


_GLOBAL_AGENT_TELEMETRY: AgentTelemetry | None = None
_GLOBAL_AGENT_TELEMETRY_LOCK = threading.Lock()


def get_global_agent_telemetry() -> AgentTelemetry:
    """Return or initialize the process-wide AgentTelemetry singleton."""

    global _GLOBAL_AGENT_TELEMETRY
    if _GLOBAL_AGENT_TELEMETRY is None:
        with _GLOBAL_AGENT_TELEMETRY_LOCK:
            if _GLOBAL_AGENT_TELEMETRY is None:
                _GLOBAL_AGENT_TELEMETRY = AgentTelemetry()
    return _GLOBAL_AGENT_TELEMETRY


def bind_global_agent_telemetry(
    *,
    metrics: Metrics | None = None,
    tracer: Tracer | None = None,
    enabled: bool | None = None,
) -> AgentTelemetry:
    """Bind the composition root's adapters to the process-wide telemetry.

    API routes, scripts, consensus, and routing all reach for the global
    instance. Returning that same object from the container prevents the
    classic split-brain where events are recorded on one instance while
    ``/metrics`` renders another, empty one.
    """

    global _GLOBAL_AGENT_TELEMETRY
    with _GLOBAL_AGENT_TELEMETRY_LOCK:
        if _GLOBAL_AGENT_TELEMETRY is None:
            _GLOBAL_AGENT_TELEMETRY = AgentTelemetry(metrics=metrics, tracer=tracer, enabled=enabled)
            return _GLOBAL_AGENT_TELEMETRY

        telemetry = _GLOBAL_AGENT_TELEMETRY
        if metrics is not None and metrics is not telemetry.metrics:
            telemetry.metrics = metrics
        if tracer is not None and tracer is not telemetry.tracer:
            telemetry.tracer = tracer
        if enabled is not None:
            telemetry.enabled = enabled
        elif os.getenv("NEXUS_OTEL_ENABLED", "false").lower() == "true":
            telemetry.enabled = True
        return telemetry
