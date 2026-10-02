"""The ReAct prompt is the single source of truth for agent behavior, so it must not lie.

`test_docs_env_vars.py` and `test_docs_cli_commands.py` hold the docs to the
code. This holds the **prompt** to the code, which is the same relationship one
level down: `REACT_SYSTEM_PROMPT` teaches the model a tool-call format, and
`process_message._parse_tool_call` enforces it. If the prompt's examples drift
from what the parser accepts, every local model that copies the example
faithfully produces a call the loop rejects - and the only symptom is the agent
losing a turn to a SYNTAX ERROR nudge.

Found on first run: the `git_info` example was `{"tool_id": "git_info",
{"repo_path": "."}}` - valid-looking JSON with the `"params":` key missing, the
only malformed example in the prompt. The parser's own error message documents
the correct format, so the example now matches it.

Two directions:
* Every `TOOL_CALL:` example in the prompt must parse and carry `tool_id` +
  `params`. Checked generically by extraction, not a hand-list of examples.
* Every tool the prompt advertises must resolve through the *real* registry -
  the same `BuiltinToolRegistry.get()` path the ReAct loop uses. A tool id that
  only exists in the prompt is the prompt advertising a capability the agent
  does not have.
"""

from __future__ import annotations

import json
import re

from nexus.application.cortex.react_prompt import REACT_SYSTEM_PROMPT, build_react_prompt

# Examples are one per line; the JSON payload runs to end of line.
TOOL_CALL_EXAMPLE = re.compile(r"TOOL_CALL:\s*(\{.*\})")


def _advertised_tool_ids() -> dict[str, int]:
    """tool_id -> prompt line number, for every example in the prompt."""
    found: dict[str, int] = {}
    for lineno, line in enumerate(REACT_SYSTEM_PROMPT.splitlines(), 1):
        match = TOOL_CALL_EXAMPLE.search(line)
        if not match:
            continue
        try:
            call = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue  # reported by the JSON test, not here
        if isinstance(call, dict) and "tool_id" in call:
            tool_id = str(call["tool_id"])
            if tool_id == "tool_name":
                continue  # the TOOL CALL FORMAT template, not an advertised tool
            found.setdefault(tool_id, lineno)
    return found


def test_the_extraction_actually_finds_examples():
    """If the extraction rots, the two real checks below pass on nothing."""
    examples = len(_advertised_tool_ids())
    assert examples >= 8, f"only {examples} TOOL_CALL examples found - extraction is stale"


def test_every_tool_call_example_in_the_prompt_is_valid_json():
    """A model copies these examples faithfully; a broken one teaches a broken call."""
    broken = []
    for lineno, line in enumerate(REACT_SYSTEM_PROMPT.splitlines(), 1):
        match = TOOL_CALL_EXAMPLE.search(line)
        if not match:
            continue
        try:
            call = json.loads(match.group(1))
        except json.JSONDecodeError as err:
            broken.append(f"  line {lineno}: not valid JSON ({err}): {line.strip()}")
            continue
        missing = [key for key in ("tool_id", "params") if key not in call]
        if missing:
            broken.append(f"  line {lineno}: missing {missing}: {line.strip()}")
    assert not broken, (
        "TOOL_CALL examples the parser will reject - fix the prompt, the parser's"
        " SYNTAX ERROR message documents the expected shape:\n" + "\n".join(broken)
    )


def test_every_tool_advertised_in_the_prompt_resolves_in_the_real_registry():
    """The prompt must not advertise a capability the agent cannot call."""
    import asyncio

    from nexus.infrastructure.adapters.execution.builtin_tools import (
        BuiltinToolRegistry,
        default_builtin_tools,
    )

    registry = BuiltinToolRegistry(default_builtin_tools())

    async def _resolve(tool_id: str):
        return await registry.get(tool_id)

    missing = [
        f"  {tool_id} (prompt line {lineno})"
        for tool_id, lineno in sorted(_advertised_tool_ids().items(), key=lambda kv: kv[1])
        if asyncio.run(_resolve(tool_id)) is None
    ]
    assert not missing, (
        "tools advertised in REACT_SYSTEM_PROMPT that the runtime registry cannot"
        " resolve - add the tool or fix the prompt:\n" + "\n".join(missing)
    )


def test_build_react_prompt_orders_system_then_user():
    messages = build_react_prompt("what is this repo?")
    assert messages[0]["role"] == "system" and messages[0]["content"] is REACT_SYSTEM_PROMPT
    assert messages[-1] == {"role": "user", "content": "what is this repo?"}
    assert len(messages) == 2


def test_build_react_prompt_includes_optional_sections_in_order():
    messages = build_react_prompt(
        "hi", tool_catalog="- tool_a: does a thing", context_additions="extra context"
    )
    assert "- tool_a: does a thing" in messages[1]["content"]
    assert messages[2]["content"] == "extra context"
    assert messages[-1]["role"] == "user"
    assert [m["role"] for m in messages] == ["system", "system", "system", "user"]
