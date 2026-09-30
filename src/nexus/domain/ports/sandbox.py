"""
Sandbox port - isolated execution for code testing during dreaming simulation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Sandbox(ABC):
    """Runs untrusted code safely (used for tool tests and dream simulation)."""

    @abstractmethod
    async def run(self, code: str, inputs: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
        """Execute code, returning {output, error, duration_ms}."""
        ...

    @abstractmethod
    async def run_code(self, code: str, timeout: int = 30) -> dict[str, Any]:
        """Execute raw python code in the sandbox, returning {output, error, duration_ms}."""
        ...

    @abstractmethod
    async def run_project(
        self, files: dict[str, str], test_command: str = "python -m pytest -q", timeout: int = 120
    ) -> dict[str, Any]:
        """Run a multi-file project (microservice scaffold) and execute its tests.

        `files` maps relative paths (e.g. "main.py", "tests/test_main.py") to source.
        Returns {output, error, duration_ms} - empty error means all tests passed.
        """
        ...
