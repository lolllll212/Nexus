"""Immutable JSON schema value objects for tool contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class JSONSchema:
    """A JSON schema used as a tool's input/output contract."""

    type: str = "object"
    properties: Dict[str, Any] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    description: str = ""

    def validate(self, data: Dict[str, Any]) -> List[str]:
        """Validate data against the schema. Returns list of errors (empty = valid)."""
        errors: List[str] = []
        for req in self.required:
            if req not in data:
                errors.append(f"Missing required field: {req}")
        for key in data:
            if key not in self.properties:
                errors.append(f"Unexpected field: {key}")
        return errors
