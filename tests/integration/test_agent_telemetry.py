from __future__ import annotations

from nexus.infrastructure.adapters.observability.agent_telemetry import AgentTelemetry


def test_agent_telemetry_tracks_agent_lifecycle_events(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_OTEL_ENABLED", "true")
    telemetry = AgentTelemetry()

    telemetry.record_route("primary", agent="xenom")
    telemetry.record_heal_cycle("ok", 0.75, agent="xenom")
    telemetry.record_consensus_round("approved", agent="ceo")
    telemetry.record_token_spend("xenom", 240, model="local")

    rendered = telemetry.render_prometheus()

    assert "nexus_route_hits_total" in rendered
    assert "nexus_heal_cycles_total" in rendered
    assert "nexus_consensus_rounds_total" in rendered
    assert "nexus_token_spend_total" in rendered


def test_agent_telemetry_is_disabled_when_env_gate_is_off(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_OTEL_ENABLED", "false")
    telemetry = AgentTelemetry()

    telemetry.record_route("local")
    telemetry.record_heal_cycle("failed", 0.25)

    assert telemetry.enabled is False
    assert telemetry.render_prometheus() == ""


def test_agent_telemetry_spans_emitted_only_when_otel_enabled(monkeypatch) -> None:
    from nexus.domain.ports.observability import NoopTracer
    from nexus.infrastructure.adapters.observability.observability import LoggingTracer

    # Disabled: NoopTracer with zero overhead
    monkeypatch.setenv("NEXUS_OTEL_ENABLED", "false")
    disabled = AgentTelemetry()
    assert isinstance(disabled.tracer, NoopTracer)
    noop_span = disabled.heal_span("astra", "failed")
    assert noop_span.name == "nexus.heal_iteration"

    # Enabled: real tracer active
    monkeypatch.setenv("NEXUS_OTEL_ENABLED", "true")
    enabled = AgentTelemetry()
    assert isinstance(enabled.tracer, LoggingTracer)
    span = enabled.consensus_span("patch-001", "tron")
    assert span.name == "nexus.consensus_round"
    assert span.attributes.get("proposal_id") == "patch-001"
    assert span.attributes.get("author") == "tron"


async def test_agent_telemetry_counters_exposed_at_metrics_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_OTEL_ENABLED", "true")
    from nexus.infrastructure.adapters.observability.agent_telemetry import get_global_agent_telemetry
    from nexus.infrastructure.api.routes.telemetry import generate_prometheus_metrics
    from tests.fakes.container import FakeContainer

    telemetry = get_global_agent_telemetry()
    telemetry.enabled = True
    telemetry.record_route("primary", agent="xenom")
    telemetry.record_heal_cycle("ok", 0.45, agent="xenom")
    telemetry.record_consensus_round("approved", duration_seconds=1.2, agent="ceo")
    telemetry.record_token_spend("tron", 500, model="qwen3.5-9b")

    container = FakeContainer()
    output = await generate_prometheus_metrics(container)

    assert "nexus_route_hits_total" in output
    assert 'route="primary"' in output
    assert "nexus_heal_cycles_total" in output
    assert 'outcome="ok"' in output
    assert "nexus_consensus_rounds_total" in output
    assert 'verdict="approved"' in output
    assert "nexus_token_spend_total" in output
    assert 'agent="tron"' in output
