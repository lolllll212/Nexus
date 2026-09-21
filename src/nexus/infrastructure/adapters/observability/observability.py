"""Observability adapters - structured JSON logging, tracing, in-memory metrics.

- LoggingTracer emits span_start/span_end as structured JSON with trace/span
  IDs propagated via contextvars so nested spans share one trace.
- InMemoryMetrics renders a Prometheus-compatible text exposition for /metrics.
"""

from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from nexus.domain.ports.observability import Metrics, Span, Tracer

_TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar("nexus_trace_id", default="")
_SPAN_ID: contextvars.ContextVar[str] = contextvars.ContextVar("nexus_span_id", default="")

_logger = logging.getLogger("nexus.trace")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
        }
        message = record.getMessage()
        try:
            parsed = json.loads(message)
            if isinstance(parsed, dict):
                payload.update(parsed)
            else:
                payload["message"] = message
        except json.JSONDecodeError:
            payload["message"] = message
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO, json_format: bool = True) -> None:
    """Install a root handler once. Safe to call repeatedly."""
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        if json_format:
            handler.setFormatter(_JsonFormatter())
        root.addHandler(handler)
    root.setLevel(level)
    _logger.setLevel(level)
    _logger.propagate = True


class _LoggingSpan(Span):
    def __init__(self, name: str, attributes: Optional[Dict[str, Any]], start_time: float, emitter) -> None:
        super().__init__(name)
        self.attributes = dict(attributes or {})
        self._emitter = emitter
        self._start = start_time
        self._tokens: Tuple = ()

    async def __aenter__(self) -> "Span":
        trace_id = _TRACE_ID.get() or str(uuid.uuid4())
        parent = _SPAN_ID.get()
        span_id = str(uuid.uuid4())
        self._tokens = (_TRACE_ID.set(trace_id), _SPAN_ID.set(span_id))
        self.attributes.update({"trace_id": trace_id, "span_id": span_id, "parent_span_id": parent or None})
        self._emitter("span_start", self.attributes)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        duration_ms = round((time.perf_counter() - self._start) * 1000, 3)
        self.attributes["duration_ms"] = duration_ms
        if exc is not None:
            self.attributes["error"] = type(exc).__name__
        self._emitter("span_end", self.attributes)
        for token in self._tokens:
            token.var.reset(token.token)
        return False


class LoggingTracer(Tracer):
    """Tracer backed by structured JSON log lines."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._log = logger or _logger

    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
        return _LoggingSpan(name, attributes, time.perf_counter(), self._emit)

    def _emit(self, event: str, attrs: Dict[str, Any]) -> None:
        self._log.info(json.dumps({"event": event, **attrs}, default=str))


def _fmt_labels(labels: Optional[Dict[str, str]]) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{k}="{v}"' for k, v in sorted(labels.items())) + "}"


class InMemoryMetrics(Metrics):
    """Metrics in process memory - suitable for single-node deployments."""

    def __init__(self) -> None:
        self._counters: Dict[Tuple, float] = defaultdict(float)
        self._gauges: Dict[Tuple, float] = {}
        self._histograms: Dict[Tuple, List[float]] = defaultdict(list)

    def _key(self, name: str, labels: Optional[Dict[str, str]]) -> Tuple:
        labels = labels or {}
        return (name, tuple(sorted(labels.items())))

    def counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        self._counters[self._key(name, labels)] += value

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        self._histograms[self._key(name, labels)].append(float(value))

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        self._gauges[self._key(name, labels)] = float(value)

    def render(self) -> str:
        lines: List[str] = []
        for (name, labels), value in sorted(self._counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name}{_fmt_labels(dict(labels))} {value}")
        for (name, labels), value in sorted(self._gauges.items()):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{_fmt_labels(dict(labels))} {value}")
        for (name, labels), values in sorted(self._histograms.items()):
            total = sum(values)
            lines.append(f"# TYPE {name} histogram")
            lines.append(f"{name}_count{_fmt_labels(dict(labels))} {len(values)}")
            lines.append(f"{name}_sum{_fmt_labels(dict(labels))} {total}")
        return "\n".join(lines) + "\n" if lines else ""
