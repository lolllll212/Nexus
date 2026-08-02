"""Observability ports - tracing and metrics for the application layer.

The application layer emits spans and counters through these abstractions.
Noop implementations ship in the port module so use cases can default to
"quiet" without ever importing infrastructure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class Span:
    """A unit of traced work; async context manager so spans nest cleanly."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.attributes: Dict[str, Any] = {}

    async def __aenter__(self) -> "Span":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value


class Tracer(ABC):
    """Records structured spans of execution (logs, traces)."""

    @abstractmethod
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Span: ...


class Metrics(ABC):
    """Time-series counters and histograms rendered for /metrics."""

    @abstractmethod
    def counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None: ...

    @abstractmethod
    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None: ...

    @abstractmethod
    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None: ...

    @abstractmethod
    def render(self) -> str: ...


class NoopTracer(Tracer):
    """Swallow spans - used when observability is not configured."""

    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> Span:
        return Span(name)


class NoopMetrics(Metrics):
    """Swallow metric points - used when observability is not configured."""

    def counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        return None

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        return None

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        return None

    def render(self) -> str:
        return ""
