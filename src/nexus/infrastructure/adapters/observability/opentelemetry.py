"""OpenTelemetry observability adapter.

Requires: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp

Set NEXUS_OTEL_ENABLED=true and NEXUS_OTEL_ENDPOINT=http://localhost:4317 to activate.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from nexus.domain.ports.observability import Metrics, Span, Tracer

_logger = logging.getLogger("nexus.otel")


class OTELTracer(Tracer):
    """Tracer backed by OpenTelemetry SDK."""

    def __init__(self, service_name: str = "nexus") -> None:
        self._service_name = service_name
        self._tracer = None
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider()
            processor = BatchSpanProcessor(_create_exporter())
            provider.add_span_processor(processor)
            trace.set_tracer_provider(provider)
            self._tracer = trace.get_tracer(service_name)
        except Exception as exc:
            _logger.warning("OpenTelemetry unavailable, falling back to logging: %s", exc)

    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
        if self._tracer is None:
            return _FallbackSpan(name, attributes)
        return _OTELSpan(self._tracer, name, attributes)


class _OTELSpan(Span):
    def __init__(self, tracer, name: str, attributes: Optional[Dict[str, Any]]) -> None:
        super().__init__(name)
        self._otel_tracer = tracer
        self._otel_span = None
        self._init_attrs = dict(attributes or {})

    async def __aenter__(self) -> "Span":
        self._otel_span = self._otel_tracer.start_span(self._name)
        for k, v in self._init_attrs.items():
            self._otel_span.set_attribute(k, str(v))
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self._otel_span:
            if exc is not None:
                self._otel_span.set_attribute("error", type(exc).__name__)
            self._otel_span.end()
        return False


class _FallbackSpan(Span):
    """Logging fallback when OTEL is unavailable."""

    async def __aenter__(self) -> "Span":
        _logger.info("span_start", {"name": self.name, **self.attributes})
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        _logger.info("span_end", {"name": self.name, **self.attributes})
        return False


class OTELMetrics(Metrics):
    """Metrics backed by OpenTelemetry SDK."""

    def __init__(self, service_name: str = "nexus") -> None:
        self._metrics = {}
        try:
            from opentelemetry import metrics
            from opentelemetry.sdk.metrics import MeterProvider

            provider = MeterProvider()
            metrics.set_meter_provider(provider)
            meter = metrics.get_meter(service_name)
            self._meter = meter
            self._counters = {}
            self._histograms = {}
            self._gauges = {}
        except Exception as exc:
            _logger.warning("OpenTelemetry metrics unavailable: %s", exc)
            self._meter = None
            self._counters = {}
            self._histograms = {}
            self._gauges = {}

    def counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        if self._meter and name not in self._counters:
            self._counters[name] = self._meter.create_counter(name)
        if name in self._counters:
            self._counters[name].add(value, labels or {})

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        if self._meter and name not in self._histograms:
            self._histograms[name] = self._meter.create_histogram(name)
        if name in self._histograms:
            self._histograms[name].record(value, labels or {})

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        # OTel gauge requires observable gauge — fall back to counter for now
        pass

    def render(self) -> str:
        return ""


def _create_exporter():
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        import os

        endpoint = os.getenv("NEXUS_OTEL_ENDPOINT", "http://localhost:4317")
        return OTLPSpanExporter(endpoint=endpoint)
    except Exception:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        return ConsoleSpanExporter()
