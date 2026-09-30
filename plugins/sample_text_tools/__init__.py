"""
Sample plugin — demonstrates the NEXUS plugin format.

To use: place this folder (or any folder with the same structure)
under the NEXUS plugins directory (default: ./plugins/).

Each plugin exposes:
    TOOLS: list[Tool]          — tool definitions
    HANDLERS: dict[str, func]  — async handler functions
"""

from __future__ import annotations

from typing import Any, Dict, List

from nexus.domain.entities.tool import Tool, ToolStatus
from nexus.domain.value_objects.schema import JSONSchema


TOOLS: List[Tool] = [
    Tool(
        id="word_count",
        name="word_count",
        description="Count words, lines, and characters in a text.",
        input_schema=JSONSchema(
            properties={"text": {"type": "string"}},
            required=["text"],
        ),
        output_schema=JSONSchema(
            properties={
                "words": {"type": "integer"},
                "lines": {"type": "integer"},
                "chars": {"type": "integer"},
            }
        ),
        status=ToolStatus.READY,
    ),
    Tool(
        id="capitalize",
        name="capitalize",
        description="Capitalize the first letter of each word in a text.",
        input_schema=JSONSchema(
            properties={"text": {"type": "string"}},
            required=["text"],
        ),
        output_schema=JSONSchema(properties={"result": {"type": "string"}}),
        status=ToolStatus.READY,
    ),
]


async def _word_count(params: Dict[str, Any]) -> Dict[str, Any]:
    text = params["text"]
    return {
        "words": len(text.split()),
        "lines": text.count("\n") + 1,
        "chars": len(text),
    }


async def _capitalize(params: Dict[str, Any]) -> Dict[str, Any]:
    return {"result": params["text"].title()}


HANDLERS: Dict[str, Any] = {
    "word_count": _word_count,
    "capitalize": _capitalize,
}
