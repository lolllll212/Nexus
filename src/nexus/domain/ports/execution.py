"""
Execution ports - tool invocation contracts.

Re-exported from tool_registry for import clarity. The application layer
injects a ToolExecutor; the infrastructure provides it.
"""

from __future__ import annotations

from nexus.domain.ports.tool_registry import ToolExecutor

__all__ = ["ToolExecutor"]
