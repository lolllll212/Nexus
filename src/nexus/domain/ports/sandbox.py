"""
Sandbox port - isolated execution for code testing during dreaming simulation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class Sandbox(ABC):
    """Runs untrusted code safely (used for tool tests and dream simulation)."""

    @abstractmethod
    async def run(self, code: str, inputs: Dict[str, Any] = None, timeout: int = 30) -> Dict[str, Any]:
        """Execute code, returning {output, error, duration_ms}."""
        ...
